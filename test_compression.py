#!/usr/bin/env python
import os
from app import compress_pdf

# Ruta del archivo
input_pdf = r'PDF\manual_k_linux.pdf'
output_pdf = r'PDF\manual_k_linux_compressed.pdf'

# Tamaño original
input_size = os.path.getsize(input_pdf) / (1024 * 1024)
print(f"📄 PDF Original: {input_size:.2f} MB")

# Comprimir
print("⏳ Comprimiendo...")
compress_pdf(input_pdf, output_pdf)

# Tamaño comprimido
output_size = os.path.getsize(output_pdf) / (1024 * 1024)
reduction = ((input_size - output_size) / input_size) * 100

print(f"📦 PDF Comprimido: {output_size:.2f} MB")
print(f"✅ Reducción: {reduction:.1f}%")
