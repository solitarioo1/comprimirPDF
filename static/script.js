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
            
            // Validar tamaño (500MB)
            if (file.size > 500 * 1024 * 1024) {
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
    form.addEventListener('submit', function(e) {
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
        
        // Obtener token CSRF del meta tag
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // Mostrar progreso
        btnCompress.disabled = true;
        btnCompress.textContent = 'Procesando...';
        progress.classList.remove('hidden');
        result.classList.add('hidden');
        
        // Simular progreso
        let progressValue = 0;
        const progressInterval = setInterval(() => {
            progressValue += 1;
            if (progressValue <= 90) {
                progressFill.style.width = progressValue + '%';
            }
        }, 200);

        // Enviar petición
        fetch('/compress', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            },
            body: formData
        })
        .then(response => {
            clearInterval(progressInterval);
            progressFill.style.width = '100%';

            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Error en el servidor');
                });
            }
            
            return response.blob();
        })
        .then(blob => {
            // Descargar archivo
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'compressed_' + fileInput.files[0].name;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showResult('¡PDFs comprimidos correctamente! Descarga iniciada.', 'success');
            
            // Resetear formulario
            form.reset();
            fileName.textContent = '';
        })
        .catch(error => {
            showResult('Error: ' + error.message, 'error');
        })
        .finally(() => {
            btnCompress.disabled = false;
            btnCompress.textContent = 'Comprimir PDFs';
            progress.classList.add('hidden');
            progressFill.style.width = '0%';
        });
    });

    function showResult(message, type) {
        result.textContent = message;
        result.className = 'result ' + type;
        result.classList.remove('hidden');
    }
});
