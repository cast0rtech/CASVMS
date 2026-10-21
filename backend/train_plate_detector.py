#!/usr/bin/env python3
# ==============================================================================
# CASVMS - YOLOv8 License Plate Detector Training & OpenVINO Export Pipeline
# ==============================================================================
import os
import sys
import shutil
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CASVMS.Train.ALPR")

def train_and_export_plate_detector(
    data_yaml: str = "vms_training/data.yaml",
    base_model: str = "yolov8n.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch_size: int = 16,
    device: str = "0",
    export_imgsz: int = 320,
    output_dir: str = "yolov8n_license_plates_openvino_model"
):
    """
    Entrena un detector YOLOv8 especializado en la clase 'license_plate'
    y lo compila automáticamente a OpenVINO FP16 para ejecución en la iGPU de Intel.
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("Se requiere la librería 'ultralytics'. Instale con: pip install ultralytics")
        sys.exit(1)

    if not os.path.exists(data_yaml):
        # Probar ruta alternativa en la raíz o contenedor
        alt_paths = [
            os.path.join(os.path.dirname(__file__), "..", data_yaml),
            "/vms_training/data.yaml",
            os.path.join(os.getcwd(), data_yaml)
        ]
        found = False
        for alt in alt_paths:
            if os.path.exists(alt):
                data_yaml = alt
                found = True
                break
        if not found:
            logger.error(f"No se encontró el archivo de configuración del dataset: {data_yaml}")
            sys.exit(1)

    logger.info(f"-> Iniciando pipeline de entrenamiento ALPR con dataset: {data_yaml}")
    logger.info(f"   Modelo base: {base_model} | Épocas: {epochs} | imgsz: {imgsz} | batch: {batch_size}")

    # 1. Cargar pesos pre-entrenados para Transfer Learning
    model = YOLO(base_model)

    # 2. Hiperparámetros de aumento adaptados a cámaras de parking y viales
    train_args = {
        "data": data_yaml,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch_size,
        "device": device,
        "workers": 4,
        "optimizer": "AdamW",
        "lr0": 0.002,
        "lrf": 0.01,
        # Aumentos geométricos y fotométricos específicos para placas de matrícula
        "degrees": 10.0,       # Rotación para cámaras en ángulo lateral
        "perspective": 0.0005, # Deformación de perspectiva
        "hsv_h": 0.015,
        "hsv_s": 0.5,          # Variaciones de color y saturación
        "hsv_v": 0.4,          # Resistencia a sombras y faros nocturnos
        "mosaic": 0.5,         # Composición de contexto
        "mixup": 0.1,
        "project": "runs/detect",
        "name": "alpr_swiss_es",
        "exist_ok": True,
        "verbose": True
    }

    logger.info("-> Entrenando red neuronal convolucional...")
    results = model.train(**train_args)
    logger.info("-> Entrenamiento completado con éxito.")

    # 3. Validación y Métricas
    metrics = model.val()
    logger.info(f"-> Validación mAP50: {metrics.box.map50:.4f} | mAP50-95: {metrics.box.map:.4f}")

    # 4. Exportación a OpenVINO FP16 para la iGPU de Intel
    logger.info(f"-> Exportando a OpenVINO FP16 (imgsz={export_imgsz}) para aceleración Edge...")
    try:
        exported_path = model.export(
            format="openvino",
            half=True,           # Precisión FP16 para optimizar ancho de banda de memoria en iGPU
            imgsz=export_imgsz   # imgsz=320 para inferencia micro ultrarrápida (< 5ms)
        )
        logger.info(f"-> Exportación completada en: {exported_path}")

        # 5. Mover/Copiar a la carpeta estándar esperada por camera_worker_dual_ai
        if exported_path and os.path.exists(exported_path):
            if os.path.abspath(exported_path) != os.path.abspath(output_dir):
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                shutil.copytree(exported_path, output_dir)
                logger.info(f"-> Modelo listo para producción en: {output_dir}")
        else:
            logger.warning(f"La ruta exportada no se localizó directamente: {exported_path}")

    except Exception as exp_err:
        logger.error(f"Error durante la exportación a OpenVINO: {exp_err}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entrenador y Exportador OpenVINO para Detector de Matrículas")
    parser.add_argument("--data", default="vms_training/data.yaml", help="Ruta a data.yaml")
    parser.add_argument("--model", default="yolov8n.pt", help="Pesos iniciales YOLO")
    parser.add_argument("--epochs", type=int, default=100, help="Número de épocas")
    parser.add_argument("--imgsz", type=int, default=640, help="Resolución de entrenamiento")
    parser.add_argument("--batch", type=int, default=16, help="Tamaño de lote (batch size)")
    parser.add_argument("--device", default="cpu", help="Dispositivo (cpu, 0, mps)")
    parser.add_argument("--export-imgsz", type=int, default=320, help="Resolución de inferencia OpenVINO")
    parser.add_argument("--output", default="yolov8n_license_plates_openvino_model", help="Directorio destino del modelo OpenVINO")

    args = parser.parse_args()

    train_and_export_plate_detector(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch_size=args.batch,
        device=args.device,
        export_imgsz=args.export_imgsz,
        output_dir=args.output
    )
