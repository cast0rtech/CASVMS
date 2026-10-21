#!/usr/bin/env python3
# ==============================================================================
# CASVMS - YOLOv8 OpenVINO FP16 Model Exporter
# ==============================================================================
import os
import sys
import shutil
import argparse
from ultralytics import YOLO

def export_model(
    weights_path: str = "runs/detect/alpr_swiss_es/weights/best.pt",
    half: bool = True,
    imgsz: int = 320,
    target_dir: str = "yolov8n_license_plates_openvino_model"
):
    print(f"-> Localizando pesos entrenados en: {weights_path}")
    if not os.path.exists(weights_path):
        # Intentar ruta relativa desde raíz si se ejecuta dentro de vms_training/
        alt_paths = [
            os.path.join("..", weights_path),
            os.path.join(os.getcwd(), weights_path),
            f"../{weights_path}"
        ]
        found = False
        for alt in alt_paths:
            if os.path.exists(alt):
                weights_path = alt
                found = True
                break
        if not found:
            print(f"[ERROR] No se encontraron los pesos en {weights_path}.")
            print("        Asegúrate de que el entrenamiento ha concluido en 'runs/detect/alpr_swiss_es/'.")
            sys.exit(1)

    # 1. Cargar los MEJORES pesos resultantes de tu entrenamiento
    print(f"-> Cargando modelo desde {weights_path}...")
    custom_model = YOLO(weights_path)

    # 2. Exportar a formato Intel OpenVINO en precisión media (FP16)
    print(f"-> Exportando a Intel OpenVINO (half={half}, imgsz={imgsz})...")
    exported_path = custom_model.export(
        format='openvino',
        half=half,
        imgsz=imgsz
    )
    print(f"-> Exportación exitosa: {exported_path}")

    # 3. Despliegue en el directorio estándar de CASVMS
    if exported_path and os.path.exists(exported_path):
        # Si se especificó target_dir, copiarlo a la raíz del proyecto
        base_target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", target_dir)
        destinations = [target_dir, os.path.normpath(base_target)]
        for dest in destinations:
            try:
                if os.path.abspath(exported_path) != os.path.abspath(dest):
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(exported_path, dest)
                    print(f"-> [OK] Modelo OpenVINO FP16 desplegado en: {dest}")
            except Exception as e:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exportador de pesos YOLOv8 a OpenVINO FP16")
    parser.add_argument("--weights", default="runs/detect/alpr_swiss_es/weights/best.pt", help="Ruta a best.pt")
    parser.add_argument("--imgsz", type=int, default=320, help="Resolución de inferencia (320 para ALPR rápido, 640 estándar)")
    parser.add_argument("--output", default="yolov8n_license_plates_openvino_model", help="Carpeta de salida")
    args = parser.parse_args()

    export_model(weights_path=args.weights, imgsz=args.imgsz, target_dir=args.output)
