# Usar una imagen base de Python ligera
# FROM python:3.9-slim-buster
FROM python:3.9-slim-bullseye


# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar los archivos de requisitos e instalar las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar navegadores para Playwright y sus dependencias a nivel del sistema operativo
# La lista de apt-get incluye dependencias comunes para ejecutar navegadores headless
# en imágenes Debian/Ubuntu slim, basada en la sugerencia de Playwright install-deps.
# --- AGREGADAS: libcups2, libpango-1.0-0, libcairo2 ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libfontconfig libdbus-1-3 \
    libglib2.0-0 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libxcb1 libxkbcommon0 libasound2 \
    libcups2 libpango-1.0-0 libcairo2 \
    # Clean up apt lists to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Instalar los binarios de los navegadores de Playwright
# Solo necesitamos chromium para este scraper.
RUN playwright install chromium

# Copiar el resto del código de la aplicación
COPY . /app

# Crear directorios para datos si no existen
RUN mkdir -p /app/data/scraped_reports /app/data/audio_reports

# Exponer el puerto en el que correrá la API
EXPOSE 8003

# Comando para ejecutar la aplicación con Uvicorn
# Se asume que main.py está en el directorio /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]