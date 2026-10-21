#!/usr/bin/env python3
# ==============================================================================
# CASVMS - ALPR License Plate Detector Training & OpenVINO Compiler
# ==============================================================================
import os
import shutil
from ultralytics import YOLO

# 1. Cargar el modelo base Nano (el más rápido y eficiente para Edge)
print("-> Descargando/Cargando pesos pre-entrenados yolov8n.pt...")
model = YOLO('yolov8n.pt')

# Determinar ruta de data.yaml (compatible ejecutando desde raíz o dentro de vms_training/)
data_path = 'data.yaml' if os.path.exists('data.yaml') else 'vms_training/data.yaml'

# 2. Iniciar el entrenamiento
print(f"-> Iniciando entrenamiento ALPR con {data_path} (100 épocas)...")
results = model.train(
    data=data_path,        # Ruta a tu archivo de configuración
    epochs=100,            # Número de pasadas completas sobre el dataset
    imgsz=640,             # Resolución de entrenamiento
    batch=16,              # Imágenes por lote (baja a 8 si falta VRAM en la GPU)
    name='alpr_swiss_es',  # Nombre de la carpeta de resultados (runs/detect/alpr_swiss_es)
    device=0,              # 0 para primera GPU NVIDIA. Usa 'cpu' o 'mps' según hardware.
    optimizer='AdamW',
    lr0=0.002,
    degrees=10.0,          # Compensación de ángulo lateral en cámaras de barrera
    perspective=0.0005,    # Deformación de perspectiva
    hsv_s=0.5,             # Resistencia a variaciones de color
    hsv_v=0.4,             # Resistencia a faros nocturnos y sombras
    verbose=True
)

# 3. Validación y Métricas
print("-> Evaluando modelo final sobre conjunto de validación...")
metrics = model.val()
print(f"   mAP50: {metrics.box.map50:.4f} | mAP50-95: {metrics.box.map:.4f}")

# 4. Exportación a OpenVINO FP16 (imgsz=320) para aceleración en iGPU Intel
print("-> Compilando a OpenVINO FP16 (imgsz=320) para latencia ultra-baja (<4ms)...")
exported_path = model.export(
    format="openvino",
    half=True,             # Precisión FP16 para ancho de banda óptimo en iGPU
    imgsz=320              # Resolución micro optimizada para recorte de matrícula
)

# 5. Despliegue automático a la carpeta del motor CASVMS
output_dir = "yolov8n_license_plates_openvino_model"
if exported_path and os.path.exists(exported_path):
    dest_dir = os.path.join(os.getcwd(), output_dir)
    if os.path.abspath(exported_path) != os.path.abspath(dest_dir):
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(exported_path, dest_dir)
        print(f"-> [LISTO] Modelo desplegado en: {dest_dir}")
        print("   El motor CASVMS (camera_worker_dual_ai) lo cargará automáticamente.")
