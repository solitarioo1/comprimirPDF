FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

LABEL traefik.http.middlewares.pdfs-buffering.buffering.maxRequestBodyBytes=1073741824
LABEL traefik.http.middlewares.pdfs-buffering.buffering.memRequestBodyBytes=1073741824
LABEL traefik.http.routers.pdfs.middlewares=pdfs-buffering
LABEL traefik.http.routers.pdfs.entrypoints=websecure

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "900", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--worker-tmp-dir", "/dev/shm", "app:app"]