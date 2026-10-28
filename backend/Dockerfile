# Backend image for hosting. Includes Tesseract OCR, which the server needs to read FDR photos and scanned PDFs.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets PORT. Locally it falls back to 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
