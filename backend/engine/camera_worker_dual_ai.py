# ==============================================================================
# CASVMS - Dual-Stage AI Camera Worker (Macro Vehicle + Micro Plate Detector)
# ==============================================================================
import os
import sys
import time
import logging
import multiprocessing as mp
from typing import Optional, Set, Any, Dict
import cv2
import numpy as np

# Asegurar importación de core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.alpr import extract_vehicle_crop, process_alpr_crop, detect_vehicle_direction

logger = logging.getLogger("CASVMS.Worker.DualAI")

def _load_yolo_model(model_path: str, task: str = "detect"):
    """Carga segura de modelos YOLO con fallback a PyTorch si no hay OpenVINO."""
    from ultralytics import YOLO
    
    # 1. Comprobar si existe la carpeta de OpenVINO directamente o con sufijo
    candidates = [
        model_path,
        f"{model_path.rstrip('/')}_openvino_model",
        "yolov8n_license_plates_openvino_model",
        "runs/detect/alpr_swiss_es/weights/best_openvino_model",
        "runs/detect/alpr_swiss_es/weights/best.pt",
        "yolov8n_openvino_model",
        "yolov8n.pt"
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return YOLO(c, task=task)
            except Exception:
                pass
                
    # Fallback si no existe en disco (descarga automática o inicialización básica)
    fallback = "yolov8n.pt"
    return YOLO(fallback, task=task)

def camera_worker_dual_ai(
    camera_id: str, 
    stream_url: str, 
    alert_queue: mp.Queue,
    stop_event: Optional[mp.Event] = None,
    shared_frames: Optional[Any] = None,
    device: str = "GPU"
):
    """
    Worker de cámara con arquitectura de IA en cascada (Dual-Stage AI):
    - PASO 1 (Inferencia Macro): Detecta personas y vehículos con YOLOv8 + ByteTrack.
    - PASO 2 (Inferencia Micro): Inferencia de alta velocidad (imgsz=320) sobre el recorte
      inferior del vehículo para localizar el bounding box exacto de la matrícula.
    - PASO 3 (Lectura OCR): EasyOCR con CLAHE/Bilateral sobre el recorte de la placa.
    - Memoria de tracks: processed_vehicles para evitar saturación de CPU/iGPU.
    """
    print(f"[{camera_id}] Iniciando Worker Dual-AI. Cargando modelos en la iGPU ({device})...")
    
    # 1. Instanciación Aislada (CRÍTICO: Hacerlo dentro del worker)
    # Modelo Principal: Detecta personas, coches, camiones (Clases COCO)
    model_general = _load_yolo_model("yolov8n_openvino_model/")
    
    # Modelo Secundario: Entrenado exclusivamente para detectar la clase "license_plate"
    model_plate = _load_yolo_model("yolov8n_license_plates_openvino_model/")
    
    # Inicializar decodificador de vídeo con baja latencia
    is_simulation = stream_url.lower() in ["demo", "sim", "none", ""]
    cap = None
    if not is_simulation:
        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    
    # Memoria temporal para no leer la misma matrícula 50 veces por segundo
    processed_vehicles: Set[int] = set()
    frame_counter = 0

    while stop_event is None or not stop_event.is_set():
        frame = None
        if cap and cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue
        else:
            # Generador sintético de prueba si no hay cámara física conectada
            frame_counter += 1
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(
                frame, 
                f"CASVMS DUAL-AI [{camera_id}] - F#{frame_counter}", 
                (50, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1.0, 
                (0, 255, 200), 
                2
            )
            time.sleep(0.04)

        # ==========================================
        # PASO 1: Inferencia Macro (Buscar Vehículos)
        # ==========================================
        try:
            results_general = model_general.track(
                frame, 
                persist=True, 
                tracker="bytetrack.yaml", 
                device=device, 
                verbose=False
            )
        except Exception as e:
            # Fallback en caso de que iGPU OpenCL no esté disponible en el host
            results_general = model_general.track(
                frame, 
                persist=True, 
                tracker="bytetrack.yaml", 
                device="cpu", 
                verbose=False
            )
        
        if results_general and len(results_general) > 0 and results_general[0].boxes.id is not None:
            boxes = results_general[0].boxes.xyxy.cpu().numpy()
            track_ids = results_general[0].boxes.id.int().cpu().numpy()
            classes = results_general[0].boxes.cls.int().cpu().numpy()

            for box, track_id, cls_id in zip(boxes, track_ids, classes):
                # 2 = Coche, 3 = Moto, 5 = Bus, 7 = Camión (COCO IDs)
                if cls_id in [2, 3, 5, 7] and track_id not in processed_vehicles:
                    # 1. Extraer recorte seguro del vehículo
                    crop = extract_vehicle_crop(frame, box, min_size=100)
                    
                    if crop is not None:
                        # 2. Análisis de masa lumínica en el vehículo (luces blancas vs rojas)
                        direction = detect_vehicle_direction(crop)
                        
                        if direction == "APPROACHING" or direction == "UNKNOWN":
                            # El vehículo viene de frente (o luces apagadas de día), procesar OCR
                            try:
                                results_plate = model_plate(
                                    crop, 
                                    device=device, 
                                    imgsz=320, 
                                    verbose=False
                                )
                            except Exception:
                                results_plate = model_plate(
                                    crop, 
                                    device="cpu", 
                                    imgsz=320, 
                                    verbose=False
                                )
                            
                            plate_boxes = results_plate[0].boxes.xyxy.cpu().numpy() if len(results_plate) > 0 else []
                            
                            if len(plate_boxes) > 0:
                                # Tomamos la chapa de matrícula detectada
                                p_box = plate_boxes[0]
                                px1, py1, px2, py2 = map(int, p_box)
                                plate_crop = crop[py1:py2, px1:px2]
                                
                                # Inferencia OCR con rumbo registrado
                                success = process_alpr_crop(plate_crop, alert_queue, camera_id, direction=direction)
                                if success:
                                    processed_vehicles.add(track_id)
                                    if len(processed_vehicles) > 500:
                                        processed_vehicles.pop()

                        elif direction == "DEPARTING":
                            # Vehículo alejándose de la barrera (pilotos traseros rojos)
                            # Se ignora el OCR para ahorrar CPU y se notifica la salida
                            alert_queue.put({
                                "type": "vehicle_departed",
                                "camera": camera_id,
                                "track_id": int(track_id)
                            })
                            processed_vehicles.add(track_id)

        # Renderizado y buffer compartido MJPEG para visualización en Tauri
        if shared_frames is not None:
            ret_enc, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret_enc:
                shared_frames[camera_id] = jpeg.tobytes()

    if cap:
        cap.release()
    print(f"[{camera_id}] Worker Dual-AI finalizado.")
