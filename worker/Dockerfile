FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libexif-dev exiftool tesseract-ocr libtesseract-dev \
    libgl1-mesa-glx libglib2.0-0 curl \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt
RUN playwright install chromium --with-deps 2>/dev/null || true

COPY backend/ /app/backend/
COPY worker/ /app/worker/
COPY providers/ /app/providers/
COPY shared/ /app/shared/

ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
