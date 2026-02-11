# Compresor de PDFs - La Positiva

Aplicación web para comprimir PDFs dentro de archivos ZIP manteniendo la estructura original de carpetas.

## Características

- Compresión inteligente según tamaño del PDF
- Mantiene estructura de carpetas y nombres
- Interfaz simple y funcional
- Validación y sanitización de entradas
- Compresión adaptativa (archivos grandes = más compresión)

## Instalación Local

### Requisitos
- Python 3.8+
- pip

### Pasos

1. Clonar repositorio:
```bash
git clone <tu-repositorio>
cd compresor-pdfs
```

2. Crear entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Ejecutar aplicación:
```bash
python app.py
```

5. Abrir navegador en `http://localhost:5000`

## Deploy en Easypanel

### Preparación

1. Subir código a GitHub

2. Crear archivo `Dockerfile` en raíz del proyecto (ver abajo)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "--workers", "2", "app:app"]
```

### Configuración Easypanel

1. Conectar repositorio GitHub
2. Seleccionar Dockerfile
3. Puerto: 5000
4. Variables de entorno (opcional):
   - `FLASK_ENV=production`
   - `MAX_CONTENT_LENGTH=524288000` (500MB)

5. Deploy

## Estructura del Proyecto

```
compresor-pdfs/
├── app.py                 # Aplicación Flask principal
├── requirements.txt       # Dependencias Python
├── templates/
│   └── index.html        # Template HTML
├── static/
│   ├── styles.css        # Estilos CSS
│   └── script.js         # JavaScript frontend
└── README.md
```

## Uso

1. Preparar archivo ZIP con PDFs organizados en carpetas
2. Subir archivo en la web
3. Esperar procesamiento
4. Descargar ZIP comprimido con misma estructura

## Compresión Inteligente

La aplicación ajusta la compresión según el tamaño:
- < 1MB: Compresión mínima (calidad 95%)
- 1-5MB: Compresión baja (calidad 85%)
- 5-10MB: Compresión media (calidad 75%)
- 10-20MB: Compresión alta (calidad 65%)
- > 20MB: Compresión máxima (calidad 50%)

## Seguridad

- Validación de extensiones de archivo
- Sanitización de nombres (secure_filename)
- Prevención de path traversal
- Límite de tamaño: 500MB
- Limpieza automática de archivos temporales

## Limitaciones

- Tamaño máximo: 500MB por archivo ZIP
- Solo acepta archivos .zip
- Los PDFs con imágenes de alta resolución se comprimen mejor

## Notas

- Archivos no-PDF dentro del ZIP se copian sin modificación
- La compresión puede variar según contenido del PDF
- PDFs con texto plano comprimen menos que PDFs con imágenes
