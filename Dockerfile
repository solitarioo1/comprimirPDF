FROM python:3.11-slim

WORKDIR /app

# Instalar Ghostscript y curl (para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de aplicación
COPY . .

# Exponer puerto
EXPOSE 5000

# Healthcheck para que EasyPanel sepa que el contenedor está listo
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# 1 worker con 4 threads: el dict jobs es compartido en el mismo proceso
# --worker-tmp-dir /dev/shm: evita falsos timeouts en filesystems overlay de Docker
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "900", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--worker-tmp-dir", "/dev/shm", "app:app"]
