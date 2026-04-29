import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis
import structlog

from backend.app.core.config import settings

logger = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based sliding window rate limiter."""

    def __init__(self, app):
        super().__init__(app)
        try:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.redis.ping()
            self.enabled = True
        except Exception:
            self.enabled = False
            logger.warning("rate_limiter_disabled", reason="Redis unavailable")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Skip health checks
        if request.url.path == "/api/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Determine limit based on endpoint
        if request.method == "POST" and "/api/jobs" in request.url.path:
            limit = settings.RATE_LIMIT_UPLOADS
            window = 60
            key = f"rl:upload:{client_ip}"
        else:
            limit = settings.RATE_LIMIT_API
            window = 60
            key = f"rl:api:{client_ip}"

        # Sliding window counter
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = pipe.execute()

        request_count = results[2]

        if request_count > limit:
            retry_after = int(window - (now - float(self.redis.zrange(key, 0, 0)[0])))
            logger.warning("rate_limit_exceeded", ip=client_ip, path=request.url.path, count=request_count)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(max(1, retry_after))},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - request_count))
        return response
