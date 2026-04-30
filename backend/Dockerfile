FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libexif-dev exiftool tesseract-ocr libtesseract-dev \
    libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY providers/ /app/providers/
COPY shared/ /app/shared/

ENV PYTHONPATH=/app

COPY backend/entrypoint.sh /app/backend/entrypoint.sh
RUN sed -i 's/\r$//' /app/backend/entrypoint.sh && chmod +x /app/backend/entrypoint.sh

CMD ["/app/backend/entrypoint.sh"]
