# 1. Usamos una imagen base ligera de Python
# Slim reduce el tamaño pero mantiene lo necesario para ML
FROM python:3.10-slim

# 2. Evitamos que Python genere archivos .pyc y habilitamos logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Directorio de trabajo en el contenedor
WORKDIR /code

# 4. Instalamos dependencias del sistema (necesarias para algunas libs de ML)
# build-essential y libgomp1 son comunes para scikit-learn/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 5. Copiamos los requirements e instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 6. Copiamos TODA la estructura del proyecto (app/, ml_models/, etc.)
COPY . .

# 7. Exponemos el puerto que usa Azure por defecto (generalmente 80 o 8000)
# Azure App Service busca el puerto 8000 o 80 automáticamente.
EXPOSE 8000

# 8. Comando de arranque
# Apuntamos al nuevo entrypoint 'app.main:app'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]