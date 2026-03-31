FROM python:3.12-slim

# Install system deps including Playwright browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexif-dev exiftool tesseract-ocr libtesseract-dev \
    libgl1 libglib2.0-0 curl \
    # Playwright Chromium dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2t64 libatspi2.0-0 libwayland-client0 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt
ENV PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000
RUN playwright install chromium

COPY backend/ /app/backend/
COPY worker/ /app/worker/
COPY providers/ /app/providers/
COPY shared/ /app/shared/

ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
