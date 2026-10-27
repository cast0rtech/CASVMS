# ==============================================================================
# CASVMS - Intel Edge AI Video Management System
# Multi-arch / Intel iGPU Acceleration Dockerfile
# ==============================================================================

FROM python:3.10-slim-bookworm

# Metadatos
LABEL maintainer="CASVMS Engineering"
LABEL description="CASVMS Backend Engine with Intel iGPU (OpenVINO + OpenCL) acceleration"

# Variables de entorno de Python y OpenVINO
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    # OpenVINO GPU device cache directory
    OV_CACHE_DIR=/app/cache/openvino_cache \
    # Configuración de hardware acceleration
    LIBVA_DRIVER_NAME=iHD

# 1. Instalación de dependencias del sistema operativo:
#    - ffmpeg y codecs multimedia
#    - Librerías base para OpenCV headless (libglib, libgl, libgomp)
#    - Drivers Intel OpenCL ICD y herramientas de diagnóstico (clinfo, vainfo)
#    - Herramientas de compilación mínimas para paquetes como lapx
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    gcc \
    g++ \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    # Intel OpenCL ICD & VA-API drivers for Intel Iris / UHD Graphics
    intel-opencl-icd \
    ocl-icd-libopencl1 \
    ocl-icd-opencl-dev \
    clinfo \
    intel-media-va-driver \
    vainfo \
    libva-drm2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# 2. Instalación de dependencias de Python
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# 3. Creación de directorios para caché de modelos, grabaciones DVR y configuración
RUN mkdir -p /app/storage/recordings /app/storage/snapshots /app/cache/openvino_cache /app/config

# 4. Copia del código fuente del backend
COPY . /app

# Exponer el puerto de FastAPI
EXPOSE 8000

# Healthcheck para validar disponibilidad del motor HTTP
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando por defecto para iniciar FastAPI con soporte Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
