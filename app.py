import os
import uuid
import zipfile
import tempfile
import shutil
import subprocess
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.utils import secure_filename

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {'zip'}

jobs: dict = {}
jobs_lock = threading.Lock()

GS_EXECUTABLE = 'gs'

def check_ghostscript() -> bool:
    candidates = ['gs', 'gswin64c', 'gswin32c']
    for cmd in candidates:
        try:
            result = subprocess.run([cmd, '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                global GS_EXECUTABLE
                GS_EXECUTABLE = cmd
                return True
        except FileNotFoundError:
            continue
    return False

GHOSTSCRIPT_AVAILABLE = check_ghostscript()

@app.before_request
def check_ghostscript_middleware():
    if not GHOSTSCRIPT_AVAILABLE and request.path == '/compress' and request.method == 'POST':
        return jsonify({'error': 'Ghostscript no está instalado en el servidor'}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_path(path):
    path = Path(path)
    if '..' in path.parts or path.is_absolute():
        raise ValueError("Path no permitido")
    return path

def get_ghostscript_params(compression_level, output_path, input_path):
    base_params = [
        GS_EXECUTABLE,
        '-sDEVICE=pdfwrite',
        '-dNOPAUSE',
        '-dBATCH',
        '-dQUIET',
        '-dDetectDuplicateImages',
        '-dCompressFonts=true',
        '-dCompressStreams=true',
        '-dEmbedAllFonts=true',
        f'-sOutputFile={output_path}'
    ]

    if compression_level == 'low':
        print("🎨 LOW: 240 DPI, PDFSETTINGS=/printer")
        base_params.extend([
            '-dPDFSETTINGS=/printer',
            '-dColorImageResolution=240',
            '-dGrayImageResolution=240',
            '-dMonoImageResolution=300',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dColorImageDownsampleThreshold=1.0',
            '-dGrayImageDownsampleThreshold=1.0',
            '-dMonoImageDownsampleThreshold=1.0',
        ])
    elif compression_level == 'medium':
        print("⚖️ MEDIUM: 120 DPI, PDFSETTINGS=/ebook")
        base_params.extend([
            '-dPDFSETTINGS=/ebook',
            '-dColorImageResolution=120',
            '-dGrayImageResolution=120',
            '-dMonoImageResolution=150',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dColorImageDownsampleThreshold=1.0',
            '-dGrayImageDownsampleThreshold=1.0',
            '-dMonoImageDownsampleThreshold=1.0',
        ])
    else:  # high
        print("⚡ HIGH: 96 DPI, PDFSETTINGS=/screen")
        base_params.extend([
            '-dPDFSETTINGS=/screen',
            '-dColorImageResolution=96',
            '-dGrayImageResolution=96',
            '-dMonoImageResolution=100',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dColorImageDownsampleThreshold=1.0',
            '-dGrayImageDownsampleThreshold=1.0',
            '-dMonoImageDownsampleThreshold=1.0',
        ])

    base_params.append(input_path)
    return base_params

def compress_pdf(input_path, output_path, compression_level='medium'):
    try:
        cmd = get_ghostscript_params(compression_level, output_path, input_path)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        if result.returncode == 0 and os.path.exists(output_path):
            input_size = os.path.getsize(input_path)
            output_size = os.path.getsize(output_path)
            ratio = (output_size / input_size) * 100
            print(f"✅ PDF comprimido: {os.path.basename(input_path)} ({ratio:.1f}%)")
            return True
        else:
            print(f"❌ Error en Ghostscript (código {result.returncode})")
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

def process_zip(input_zip_path: str, output_zip_path: str, compression_level: str = 'medium', progress_callback=None) -> dict:
    temp_extract = tempfile.mkdtemp()
    temp_compress = tempfile.mkdtemp()

    MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
    try:
        with zipfile.ZipFile(input_zip_path, 'r') as zip_ref:
            total_size = sum(info.file_size for info in zip_ref.infolist())
            if total_size > MAX_UNCOMPRESSED:
                raise ValueError(f'El ZIP descomprimido supera el límite de 2GB ({total_size // (1024**2)}MB)')
            zip_ref.extractall(temp_extract)

        all_files = [
            (root, f)
            for root, _, files in os.walk(temp_extract)
            for f in files
        ]
        total_pdfs = sum(1 for _, f in all_files if f.lower().endswith('.pdf'))
        processed_pdfs = 0
        compressed_pdfs = 0

        if progress_callback:
            progress_callback(0, total_pdfs or 1)

        for root, file in all_files:
            if file.lower().endswith('.pdf'):
                input_pdf = os.path.join(root, file)

                try:
                    rel_path = sanitize_path(os.path.relpath(input_pdf, temp_extract))
                except ValueError:
                    print(f"Path rechazado: {input_pdf}")
                    continue

                output_pdf = os.path.join(temp_compress, str(rel_path))
                os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

                if compress_pdf(input_pdf, output_pdf, compression_level):
                    compressed_pdfs += 1

                processed_pdfs += 1
                if progress_callback:
                    progress_callback(processed_pdfs, total_pdfs or 1)
            else:
                input_file = os.path.join(root, file)

                try:
                    rel_path = sanitize_path(os.path.relpath(input_file, temp_extract))
                except ValueError:
                    print(f"Path rechazado: {input_file}")
                    continue

                output_file = os.path.join(temp_compress, str(rel_path))
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                shutil.copy2(input_file, output_file)

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
        shutil.rmtree(temp_extract, ignore_errors=True)
        shutil.rmtree(temp_compress, ignore_errors=True)


def run_job(job_id: str, input_path: str, output_path: str, compression_level: str, output_filename: str) -> None:
    try:
        def progress_callback(current: int, total: int) -> None:
            with jobs_lock:
                jobs[job_id]['current'] = current
                jobs[job_id]['total'] = total

        result = process_zip(input_path, output_path, compression_level, progress_callback)

        with jobs_lock:
            if result['success']:
                jobs[job_id].update({
                    'status': 'done',
                    'output_path': output_path,
                    'output_filename': output_filename,
                })
            else:
                jobs[job_id].update({'status': 'error', 'error': 'Error procesando el archivo'})
    except Exception as e:
        with jobs_lock:
            jobs[job_id].update({'status': 'error', 'error': str(e)})
    finally:
        try:
            os.remove(input_path)
        except OSError:
            pass

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
        compression_level = request.form.get('compression', 'medium')
        if compression_level not in ['low', 'medium', 'high']:
            compression_level = 'medium'

        print(f"\n✅ Comprimiendo con nivel: {compression_level.upper()}")

        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({'error': 'Nombre de archivo inválido'}), 400

        unique_id = uuid.uuid4().hex
        input_path = os.path.join(tempfile.gettempdir(), f"{unique_id}_{filename}")
        file.save(input_path)

        if not zipfile.is_zipfile(input_path):
            os.remove(input_path)
            return jsonify({'error': 'Archivo ZIP inválido'}), 400

        output_filename = f"compressed_{filename}"
        output_path = os.path.join(tempfile.gettempdir(), f"{unique_id}_{output_filename}")

        job_id = unique_id
        with jobs_lock:
            jobs[job_id] = {
                'status': 'processing',
                'current': 0,
                'total': 0,
                'created_at': time.time()
            }

        threading.Thread(
            target=run_job,
            args=(job_id, input_path, output_path, compression_level, output_filename),
            daemon=True
        ).start()

        return jsonify({'job_id': job_id})

    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500


@app.route('/progress/<job_id>')
def job_progress(job_id):
    now = time.time()
    with jobs_lock:
        expired = [
            jid for jid, job in list(jobs.items())
            if job['status'] in ('done', 'error') and now - job.get('created_at', now) > 3600
        ]
        for jid in expired:
            output = jobs[jid].get('output_path')
            if output:
                try:
                    os.remove(output)
                except OSError:
                    pass
            del jobs[jid]
        job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job no encontrado'}), 404

    return jsonify({
        'status': job['status'],
        'current': job.get('current', 0),
        'total': job.get('total', 0),
        'error': job.get('error')
    })


@app.route('/download/<job_id>')
def job_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job or job['status'] != 'done':
        return jsonify({'error': 'Archivo no disponible'}), 404

    output_path = job['output_path']
    output_filename = job['output_filename']

    # ✅ BUG FIX: after_this_request no existe en Flask 3.x, limpiamos antes de enviar
    with jobs_lock:
        jobs.pop(job_id, None)

    response = send_file(
        output_path,
        as_attachment=True,
        download_name=output_filename,
        mimetype='application/zip'
    )

    try:
        os.remove(output_path)
    except OSError:
        pass

    return response


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'Archivo demasiado grande (máx 500MB)'}), 413

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({'error': 'Token de seguridad inválido. Recarga la página e intenta de nuevo.'}), 400

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Solicitud inválida. Por favor intenta de nuevo.'}), 400

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Error interno del servidor.'}), 500

@app.route('/test-compression', methods=['GET'])
def test_compression_endpoint():
    if os.environ.get('FLASK_DEBUG', 'false').lower() != 'true':
        return jsonify({'error': 'Not found'}), 404
    test_dir = tempfile.mkdtemp()

    try:
        test_pdf = os.path.join(test_dir, "test.pdf")
        with open(test_pdf, 'wb') as f:
            f.write(b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000333 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
427
%%EOF""")

        results = {}
        for level in ['low', 'medium', 'high']:
            output = os.path.join(test_dir, f"test_{level}.pdf")
            compress_pdf(test_pdf, output, level)
            if os.path.exists(output):
                original_size = os.path.getsize(test_pdf)
                compressed_size = os.path.getsize(output)
                ratio = (compressed_size / original_size) * 100
                results[level] = {
                    'original': original_size,
                    'compressed': compressed_size,
                    'ratio': f"{ratio:.1f}%"
                }

        return jsonify({
            'success': True,
            'results': results,
            'message': 'Prueba completada.'
        })

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)