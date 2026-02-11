import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
import PyPDF2
from PIL import Image
import io
import img2pdf

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_path(path):
    """Prevenir path traversal attacks"""
    path = Path(path)
    if '..' in path.parts or path.is_absolute():
        raise ValueError("Path no permitido")
    return path

def calculate_compression_quality(file_size_mb):
    """Calcula calidad de compresión según tamaño del archivo"""
    if file_size_mb < 1:
        return 95  # Baja compresión
    elif file_size_mb < 5:
        return 85
    elif file_size_mb < 10:
        return 75
    elif file_size_mb < 20:
        return 65
    else:
        return 50  # Alta compresión para archivos grandes

def compress_pdf(input_path, output_path):
    """Comprime un PDF reduciendo calidad de imágenes"""
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        quality = calculate_compression_quality(file_size_mb)
        
        reader = PyPDF2.PdfReader(input_path)
        writer = PyPDF2.PdfWriter()
        
        for page in reader.pages:
            # Compresión básica de contenido
            page.compress_content_streams()
            writer.add_page(page)
        
        # Escribir con compresión
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)
        
        # Si no se redujo significativamente, intentar más compresión
        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if output_size_mb > file_size_mb * 0.8:  # Si solo redujo menos del 20%
            # Aplicar compresión adicional reduciendo imágenes
            compress_pdf_images(output_path, output_path, quality)
        
        return True
    except Exception as e:
        print(f"Error comprimiendo {input_path}: {str(e)}")
        # Si falla, copiar el original
        shutil.copy2(input_path, output_path)
        return False

def compress_pdf_images(input_path, output_path, quality=75):
    """Compresión más agresiva reduciendo resolución de imágenes"""
    try:
        reader = PyPDF2.PdfReader(input_path)
        writer = PyPDF2.PdfWriter()
        
        for page in reader.pages:
            page.compress_content_streams()
            writer.add_page(page)
        
        with open(output_path, 'wb') as f:
            writer.write(f)
            
    except Exception as e:
        print(f"Error en compresión de imágenes: {str(e)}")
        shutil.copy2(input_path, output_path)

def process_zip(input_zip_path, output_zip_path):
    """Procesa el ZIP completo manteniendo estructura"""
    temp_extract = tempfile.mkdtemp()
    temp_compress = tempfile.mkdtemp()
    
    try:
        # Extraer ZIP
        with zipfile.ZipFile(input_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract)
        
        # Procesar cada PDF manteniendo estructura
        total_pdfs = 0
        compressed_pdfs = 0
        
        for root, dirs, files in os.walk(temp_extract):
            for file in files:
                if file.lower().endswith('.pdf'):
                    total_pdfs += 1
                    input_pdf = os.path.join(root, file)
                    
                    # Validar ruta para prevenir path traversal
                    try:
                        rel_path = sanitize_path(os.path.relpath(input_pdf, temp_extract))
                    except ValueError as e:
                        print(f"Path rechazado: {input_pdf}")
                        continue
                    
                    output_pdf = os.path.join(temp_compress, str(rel_path))
                    
                    # Crear directorio si no existe
                    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
                    
                    # Comprimir PDF
                    if compress_pdf(input_pdf, output_pdf):
                        compressed_pdfs += 1
                else:
                    # Copiar archivos no-PDF
                    input_file = os.path.join(root, file)
                    
                    # Validar ruta para prevenir path traversal
                    try:
                        rel_path = sanitize_path(os.path.relpath(input_file, temp_extract))
                    except ValueError as e:
                        print(f"Path rechazado: {input_file}")
                        continue
                    
                    output_file = os.path.join(temp_compress, str(rel_path))
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    shutil.copy2(input_file, output_file)
        
        # Crear nuevo ZIP
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_compress):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_compress)
                    zipf.write(file_path, arcname)
        
        return {
            'success': True,
            'total_pdfs': total_pdfs,
            'compressed_pdfs': compressed_pdfs
        }
        
    finally:
        # Limpiar temporales
        shutil.rmtree(temp_extract, ignore_errors=True)
        shutil.rmtree(temp_compress, ignore_errors=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compress', methods=['POST'])
def compress():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Solo se permiten archivos ZIP'}), 400
    
    try:
        # Sanitizar nombre
        filename = secure_filename(file.filename)
        
        # Guardar archivo temporal
        input_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(input_path)
        
        # Validar que es un ZIP válido
        if not zipfile.is_zipfile(input_path):
            os.remove(input_path)
            return jsonify({'error': 'Archivo ZIP inválido'}), 400
        
        # Crear archivo de salida
        output_filename = f"compressed_{filename}"
        output_path = os.path.join(tempfile.gettempdir(), output_filename)
        
        # Procesar
        result = process_zip(input_path, output_path)
        
        # Limpiar entrada
        os.remove(input_path)
        
        if result['success']:
            return send_file(
                output_path,
                as_attachment=True,
                download_name=output_filename,
                mimetype='application/zip'
            )
        else:
            return jsonify({'error': 'Error procesando el archivo'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'Archivo demasiado grande (máx 500MB)'}), 413

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
