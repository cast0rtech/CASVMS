# ==============================================================================
# CASVMS - YOLOv8 + OpenVINO + ByteTrack Inference Engine
# ==============================================================================
import os
import logging
from typing import List, Optional, Set
import numpy as np
from ultralytics import YOLO

from core.types import TrackedDetection

logger = logging.getLogger("CASVMS.Detector")

# Clases relevantes para vigilancia industrial y SCADA (subconjunto COCO)
DEFAULT_TARGET_CLASSES: Set[str] = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck"
}

class EdgeYOLODetector:
    """
    Motor de detección y seguimiento de objetos acelerado con OpenVINO en iGPU.
    
    Integra YOLOv8 (exportado a IR OpenVINO FP16) con el algoritmo de tracking
    ByteTrack para garantizar persistencia y trazabilidad temporal de IDs.
    """
    
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        device: str = "GPU",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        tracker_config: str = "bytetrack.yaml",
        target_classes: Optional[Set[str]] = None
    ):
        self.device = device.upper()
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.tracker_config = tracker_config
        self.target_classes = target_classes or DEFAULT_TARGET_CLASSES
        
        self.model = self._initialize_model(model_path)
        logger.info(
            f"Detector YOLOv8 cargado con éxito en dispositivo '{self.device}'. "
            f"Tracker: {self.tracker_config}, Conf: {self.conf_threshold}."
        )

    def _initialize_model(self, model_path: str) -> YOLO:
        """
        Carga el modelo. Si se especifica OpenVINO y no existe la carpeta exportada,
        procede a compilar y exportar el modelo a OpenVINO FP16 automáticamente.
        """
        try:
            # Comprobar si ya existe una versión OpenVINO exportada
            base_name, _ = os.path.splitext(model_path)
            openvino_dir = f"{base_name}_openvino_model"
            
            if os.path.exists(openvino_dir):
                logger.info(f"Cargando modelo OpenVINO pre-existente desde '{openvino_dir}'...")
                model = YOLO(openvino_dir, task="detect")
            else:
                logger.info(f"Cargando modelo base '{model_path}'...")
                base_model = YOLO(model_path)
                
                # Si el dispositivo es GPU u OpenVINO está disponible, exportamos a formato OpenVINO
                try:
                    logger.info("Exportando modelo a OpenVINO FP16 para aceleración iGPU...")
                    exported_path = base_model.export(format="openvino", half=True)
                    model = YOLO(exported_path, task="detect")
                except Exception as export_err:
                    logger.warning(
                        f"No se pudo exportar automáticamente a OpenVINO ({export_err}). "
                        f"Utilizando modelo nativo PyTorch."
                    )
                    model = base_model
                    
            return model
            
        except Exception as e:
            logger.error(f"Error crítico inicializando modelo YOLOv8: {str(e)}", exc_info=True)
            # Reintento con CPU seguro
            logger.info("Intentando fallback sobre CPU estándar...")
            self.device = "CPU"
            return YOLO(model_path)

    def track(self, frame: np.ndarray) -> List[TrackedDetection]:
        """
        Ejecuta inferencia y seguimiento ByteTrack sobre el frame proporcionado.
        
        Args:
            frame: Imagen BGR en formato NumPy array.
            
        Returns:
            List[TrackedDetection]: Lista de objetos detectados con ID asignado.
        """
        if frame is None or frame.size == 0:
            return []

        try:
            # Ejecución de YOLO con persistencia de tracker
            # device='GPU' usa OpenVINO con Intel iGPU / OpenCL
            results = self.model.track(
                source=frame,
                persist=True,
                tracker=self.tracker_config,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                device=self.device,
                verbose=False
            )
            
            detections: List[TrackedDetection] = []
            
            if not results or len(results) == 0:
                return detections

            result = results[0]
            boxes = result.boxes
            
            if boxes is None or len(boxes) == 0:
                return detections
            
            # Comprobación de existencia de IDs de tracking asignados por ByteTrack
            has_track_ids = boxes.id is not None
            track_ids = boxes.id.int().cpu().tolist() if has_track_ids else [-1] * len(boxes)
            
            xyxy_coords = boxes.xyxy.cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            class_ids = boxes.cls.int().cpu().tolist()
            names_dict = result.names

            for bbox, conf, cls_id, track_id in zip(xyxy_coords, confidences, class_ids, track_ids):
                class_name = names_dict.get(cls_id, str(cls_id))
                
                # Filtrar únicamente clases de interés industrial/seguridad
                if self.target_classes and class_name not in self.target_classes:
                    continue
                    
                detection = TrackedDetection(
                    track_id=int(track_id),
                    class_id=int(cls_id),
                    class_name=class_name,
                    confidence=float(conf),
                    bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                )
                detections.append(detection)

            return detections

        except Exception as e:
            logger.error(f"Fallo en ejecución de inferencia YOLO+ByteTrack: {str(e)}", exc_info=True)
            return []
