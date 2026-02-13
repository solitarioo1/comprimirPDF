import os
import zipfile
import tempfile
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {'zip'}

# Verificar Ghostscript disponible
def check_ghostscript():
    """Verifica si Ghostscript está instalado"""
    try:
        result = subprocess.run(['gs', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

GHOSTSCRIPT_AVAILABLE = check_ghostscript()

@app.before_request
def check_ghostscript_middleware():
    """Alerta si Ghostscript no está disponible"""
    if not GHOSTSCRIPT_AVAILABLE and request.path == '/compress':
        return jsonify({'error': 'Ghostscript no está instalado en el servidor'}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_path(path):
    """Prevenir path traversal attacks"""
    path = Path(path)
    if '..' in path.parts or path.is_absolute():
        raise ValueError("Path no permitido")
    return path

def get_ghostscript_params(compression_level, output_path, input_path):
    """Retorna parámetros de Ghostscript según nivel de compresión"""
    print(f"⚙️ DEBUG get_ghostscript_params: compression_level = '{compression_level}'")
    base_params = [
        'gs',
        '-sDEVICE=pdfwrite',
        '-dCompressPDFStreams=true',
        '-dDetectDuplicateImages',
        '-dCompressFonts=true',
        '-dDownsampleColorImages=true',
        '-dDownsampleGrayImages=true',
        '-dQUIET',
        '-dNOPAUSE',
        '-dBATCH',
        f'-sOutputFile={output_path}',
        input_path
    ]
    
    # Ajustar según nivel
    if compression_level == 'low':
        # Baja compresión - máxima calidad
        print("🎨 DEBUG: Aplicando parámetros LOW (300 DPI)")
        base_params.extend([
            '-dPDFSETTINGS=/prepress',
            '-dColorImageResolution=300',
            '-dGrayImageResolution=300',
            '-dMonoImageResolution=300',
            '-r300x300'
        ])
    elif compression_level == 'medium':
        # Media compresión - balance
        print("⚖️ DEBUG: Aplicando parámetros MEDIUM (150 DPI)")
        base_params.extend([
            '-dPDFSETTINGS=/screen',
            '-dColorImageResolution=150',
            '-dGrayImageResolution=150',
            '-dMonoImageResolution=150',
            '-r150x150'
        ])
    else:  # high/agresivo
        # Alta compresión - máxima reducción
        print("⚡ DEBUG: Aplicando parámetros HIGH (100 DPI)")
        base_params.extend([
            '-dPDFSETTINGS=/ebook',
            '-dColorImageResolution=100',
            '-dGrayImageResolution=100',
            '-dMonoImageResolution=100',
            '-r100x100',
            '-dEncodeColorImages=true',
            '-dEncodeGrayImages=true'
        ])
    
    return base_params

def compress_pdf(input_path, output_path, compression_level='medium'):
    """Comprime un PDF usando Ghostscript con nivel de compresión"""
    try:
        # Obtener parámetros según nivel
        cmd = get_ghostscript_params(compression_level, output_path, input_path)
        
        print(f"🚀 DEBUG: Ejecutando comando Ghostscript")
        print(f"   Input: {input_path}")
        print(f"   Output: {output_path}")
        print(f"   Nivel: {compression_level}")
        
        # Ejecutar con subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            input_size = os.path.getsize(input_path)
            output_size = os.path.getsize(output_path)
            ratio = (output_size / input_size) * 100
            print(f"✅ Compresión exitosa: {input_size} -> {output_size} ({ratio:.1f}%)")
            return True
        else:
            print(f"❌ Error en Ghostscript (código {result.returncode}): {result.stderr}")
            if "gs: command not found" in result.stderr or result.returncode == 127:
                print("⚠️ Ghostscript no instalado - copiando archivo sin comprimir")
            shutil.copy2(input_path, output_path)
            return False
        
    except FileNotFoundError:
        print("Ghostscript no instalado")
        shutil.copy2(input_path, output_path)
        return False
    except Exception as e:
        print(f"Error comprimiendo {input_path}: {str(e)}")
        shutil.copy2(input_path, output_path)
        return False

def compress_pdf_images(input_path, output_path, quality=75):
    """Alias para mantener compatibilidad"""
    return compress_pdf(input_path, output_path)

def process_zip(input_zip_path, output_zip_path, compression_level='medium'):
    """Procesa el ZIP completo manteniendo estructura"""
    print(f"📦 DEBUG process_zip: Nivel de compresión = '{compression_level}'")
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
                    print(f"📄 DEBUG: Procesando {file} con nivel '{compression_level}'")
                    
                    # Validar ruta para prevenir path traversal
                    try:
                        rel_path = sanitize_path(os.path.relpath(input_pdf, temp_extract))
                    except ValueError as e:
                        print(f"Path rechazado: {input_pdf}")
                        continue
                    
                    output_pdf = os.path.join(temp_compress, str(rel_path))
                    
                    # Crear directorio si no existe
                    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
                    
                    # Comprimir PDF con nivel especificado
                    if compress_pdf(input_pdf, output_pdf, compression_level):
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
        # Obtener nivel de compresión del formulario
        compression_level = request.form.get('compression', 'medium')
        print(f"🔧 DEBUG: Nivel de compresión recibido: '{compression_level}'")
        
        # Validar que sea un nivel válido
        if compression_level not in ['low', 'medium', 'high']:
            print(f"⚠️ DEBUG: Nivel inválido '{compression_level}', usando 'medium' por defecto")
            compression_level = 'medium'
        
        print(f"✅ DEBUG: Usando nivel de compresión: '{compression_level}'")
        
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
        
        # Procesar con nivel de compresión especificado
        result = process_zip(input_path, output_path, compression_level)
        
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
