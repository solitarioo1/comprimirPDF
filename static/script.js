document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const fileLabel = document.querySelector('.file-label');
    const fileName = document.querySelector('.file-name');
    const btnCompress = document.getElementById('btnCompress');
    const progress = document.getElementById('progress');
    const progressFill = document.querySelector('.progress-fill');
    const result = document.getElementById('result');

    // Actualizar nombre de archivo seleccionado
    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            const file = this.files[0];
            fileName.textContent = file.name;
            
            // Validar tamaño (1GB)
            if (file.size > 1224 * 1024 * 1024) {
                showResult('El archivo es demasiado grande. Máximo 500MB.', 'error');
                this.value = '';
                fileName.textContent = '';
                return;
            }

            // Validar extensión
            if (!file.name.toLowerCase().endsWith('.zip')) {
                showResult('Solo se permiten archivos ZIP.', 'error');
                this.value = '';
                fileName.textContent = '';
                return;
            }

            result.classList.add('hidden');
        }
    });

    // Drag and drop
    fileLabel.addEventListener('dragover', function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--naranja)';
        this.style.background = 'var(--blanco)';
    });

    fileLabel.addEventListener('dragleave', function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--gris-medio)';
        this.style.background = 'var(--gris-claro)';
    });

    fileLabel.addEventListener('drop', function(e) {
        e.preventDefault();
        this.style.borderColor = 'var(--gris-medio)';
        this.style.background = 'var(--gris-claro)';
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            const event = new Event('change');
            fileInput.dispatchEvent(event);
        }
    });

    // Enviar formulario
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (!fileInput.files.length) {
            showResult('Por favor selecciona un archivo ZIP.', 'error');
            return;
        }

        const selectedRadio = document.querySelector('input[name="compression"]:checked');
        if (!selectedRadio) {
            showResult('Error: No hay nivel de compresión seleccionado', 'error');
            return;
        }

        const compressionLevel = selectedRadio.value;
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('compression', compressionLevel);

        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        const originalFileName = fileInput.files[0].name;

        btnCompress.disabled = true;
        btnCompress.textContent = 'Procesando...';
        progress.classList.remove('hidden');
        result.classList.add('hidden');
        progressFill.style.width = '2%';

        try {
            // 1. Subir archivo → obtener job_id
            const submitRes = await fetch('/compress', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            });

            const contentType = submitRes.headers.get('content-type') || '';
            if (!submitRes.ok) {
                const msg = contentType.includes('application/json')
                    ? (await submitRes.json()).error
                    : `Error en el servidor (${submitRes.status}). Recarga la página.`;
                throw new Error(msg);
            }

            const { job_id } = await submitRes.json();

            // 2. Esperar con progreso real
            await pollProgress(job_id);

            // 3. Descargar resultado
            const dlRes = await fetch(`/download/${job_id}`);
            if (!dlRes.ok) {
                const data = await dlRes.json();
                throw new Error(data.error || 'Error descargando el archivo');
            }
            const blob = await dlRes.blob();

            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'compressed_' + originalFileName;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showResult('¡PDFs comprimidos correctamente! Descarga iniciada.', 'success');
            form.reset();
            fileName.textContent = '';

        } catch (error) {
            showResult('Error: ' + error.message, 'error');
        } finally {
            btnCompress.disabled = false;
            btnCompress.textContent = 'Comprimir PDFs';
            progress.classList.add('hidden');
            progressFill.style.width = '0%';
        }
    });

    async function pollProgress(jobId) {
        return new Promise((resolve, reject) => {
            const interval = setInterval(async () => {
                try {
                    const res = await fetch(`/progress/${jobId}`);
                    const data = await res.json();

                    if (data.status === 'done') {
                        clearInterval(interval);
                        progressFill.style.width = '100%';
                        resolve();
                    } else if (data.status === 'error') {
                        clearInterval(interval);
                        reject(new Error(data.error || 'Error en el servidor'));
                    } else if (data.total > 0) {
                        const pct = Math.max(5, Math.round((data.current / data.total) * 95));
                        progressFill.style.width = pct + '%';
                    }
                } catch (e) {
                    clearInterval(interval);
                    reject(new Error('Error de conexión con el servidor'));
                }
            }, 1000);
        });
    }

    function showResult(message, type) {
        result.textContent = message;
        result.className = 'result ' + type;
        result.classList.remove('hidden');
    }
});
