FROM python:3.11-slim

WORKDIR /app

# Instalar Ghostscript
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copiar código de aplicación
COPY . .

# Exponer puerto
EXPOSE 5000

# Ejecutar con Gunicorn - timeout aumentado para archivos grandes (15 minutos)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "900", "--workers", "2", "app:app"]
