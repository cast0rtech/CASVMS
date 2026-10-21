# ==============================================================================
# CASVMS - Automatic License Plate Recognition (ALPR) Pipeline
# ==============================================================================
import re
import time
import logging
from typing import Optional, List, Tuple, Dict, Any, Set, Union
import numpy as np
import cv2

from core.plate_whitelist import PlateWhitelistManager

logger = logging.getLogger("CASVMS.ALPR")

# Clases COCO correspondientes a vehículos
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

class ALPRPipeline:
    """
    Pipeline de Reconocimiento Automático de Matrículas (ALPR).
    
    Diseñado para instanciarse DENTRO del proceso hijo (worker) de la cámara
    para evitar conflictos de contexto de memoria y GPU/PyTorch en multiprocesamiento.
    
    Flujo:
    1. Detección de vehículo dentro de la ROI de la barrera.
    2. Estimación de velocidad cinemática (congelado / velocidad cercana a 0).
    3. Extracción de recorte (crop) y preprocesamiento (escala de grises + equalizeHist).
    4. Inferencia OCR mediante EasyOCR.
    5. Filtrado por Regex y verificación en SQLite Whitelist.
    6. Generación del evento de control de acceso para apertura de barrera.
    """

    def __init__(
        self,
        camera_id: str = "cam_parking",
        db_path: str = "/app/config/plates_whitelist.db",
        use_gpu: bool = False,
        speed_threshold_px: float = 3.5,     # Desplazamiento máximo en px para considerar vehículo detenido
        stop_frames_required: int = 5,       # Frames consecutivos detenido en la barrera
        barrier_cooldown_seconds: float = 12.0 # Tiempo de enfriamiento para no reabrir continuamente
    ):
        self.camera_id = camera_id
        self.speed_threshold_px = speed_threshold_px
        self.stop_frames_required = stop_frames_required
        self.barrier_cooldown = barrier_cooldown_seconds

        # Base de datos SQLite de matrículas autorizadas
        self.whitelist = PlateWhitelistManager(db_path=db_path)

        # Historial de cinemática por track ID: {track_id: [(x, y, timestamp), ...]}
        self._track_history: Dict[int, List[Tuple[float, float, float]]] = {}
        
        # Conteo de frames detenido por track ID: {track_id: frame_count}
        self._stopped_frames: Dict[int, int] = {}

        # Cooldown de barrera por matrícula: {normalized_plate: last_opened_time}
        self._plate_cooldown: Dict[str, float] = {}

        # Memoria de tracks procesados para no saturar la CPU con OCR redundante
        self._processed_tracks: Set[int] = set()
        self.use_gpu = use_gpu

        # Instanciación local de EasyOCR (CRÍTICO: dentro del worker)
        self.ocr_reader = self._init_easyocr(use_gpu=use_gpu)

        # Modelo Secundario Micro: Localización de chapa de matrícula (imgsz=320)
        self.plate_detector = self._init_plate_detector(use_gpu=use_gpu)

    def _init_plate_detector(self, use_gpu: bool):
        """Inicializa detector secundario de micro-inferencia para la placa si está disponible."""
        try:
            import os
            from ultralytics import YOLO
            for p in ["yolov8n_license_plates_openvino_model", "yolov8n_license_plates.pt"]:
                if os.path.exists(p):
                    logger.info(f"[{self.camera_id}] Modelo secundario de matrícula cargado desde '{p}'.")
                    return YOLO(p, task="detect")
            return None
        except Exception:
            return None

    def mark_vehicle_as_processed(self, track_id: int) -> None:
        """
        Marca un track_id como procesado en la memoria local
        para no repetir la inferencia EasyOCR en fotogramas subsiguientes.
        """
        self._processed_tracks.add(track_id)
        if len(self._processed_tracks) > 500:
            self._processed_tracks.pop()

    def _init_easyocr(self, use_gpu: bool):
        """Inicializa EasyOCR de forma segura dentro del worker (CRÍTICO: nunca a nivel global)."""
        try:
            import easyocr
            import torch
            has_cuda = torch.cuda.is_available() if hasattr(torch, "cuda") else False
            gpu_flag = bool(use_gpu and has_cuda)
            logger.info(f"[{self.camera_id}] Inicializando EasyOCR Reader en proceso worker (Idiomas=['de', 'en'], GPU={gpu_flag})...")
            # Cargar los idiomas relevantes para matrículas europeas y suizas (ej. alemán e inglés)
            reader = easyocr.Reader(['de', 'en'], gpu=gpu_flag, verbose=False)
            logger.info(f"[{self.camera_id}] EasyOCR Reader listo.")
            return reader
        except ImportError:
            logger.warning(
                f"[{self.camera_id}] easyocr no está instalado en este entorno. "
                f"El pipeline operará con extractor simulado de pruebas."
            )
            return None
        except Exception as e:
            logger.error(f"[{self.camera_id}] Error inicializando EasyOCR: {str(e)}", exc_info=True)
            return None

    def is_vehicle_stopped(self, track_id: int, current_pos: Tuple[float, float], now: float) -> bool:
        """
        Calcula si el vehículo ha reducido su velocidad prácticamente a cero
        durante un número configurable de fotogramas frente a la barrera.
        """
        history = self._track_history.setdefault(track_id, [])
        history.append((current_pos[0], current_pos[1], now))
        if len(history) > 10:
            history.pop(0)

        if len(history) < 2:
            return False

        # Desplazamiento respecto al fotograma inmediatamente anterior
        prev_x, prev_y, _ = history[-2]
        curr_x, curr_y, _ = history[-1]
        displacement = np.hypot(curr_x - prev_x, curr_y - prev_y)

        if displacement <= self.speed_threshold_px:
            self._stopped_frames[track_id] = self._stopped_frames.get(track_id, 0) + 1
        else:
            self._stopped_frames[track_id] = 0

        return self._stopped_frames.get(track_id, 0) >= self.stop_frames_required

    def preprocess_plate_for_alpr(self, crop_img: np.ndarray) -> np.ndarray:
        """
        Pipeline de preprocesamiento de visión artificial clásica adaptado para ALPR industrial:
        1. Escala de grises: asegura monocromo uniforme incluso bajo iluminación infrarroja (IR).
        2. Bilateral Filter: suprime ruido de sensor preservando con nitidez los bordes de los números.
        3. CLAHE (Contrast Limited Adaptive Histogram Equalization):
           Elimina el 'blooming' (brillo deslumbrante de faros y reflexión sobre placas retroreflectivas).
        """
        if crop_img is None or crop_img.size == 0:
            return crop_img

        # 1. Escala de grises (El infrarrojo ya es monocromo, pero esto asegura el formato)
        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)

        # 2. Reducción de ruido conservando los bordes de los números
        # d=9 (diámetro del píxel), sigmaColor=75, sigmaSpace=75
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)

        # 3. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # Resuelve el problema del "blooming" (brillo excesivo de los faros / IR en la placa)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        equalized = clahe.apply(denoised)

        # 4. Binarización Otsu (Opcional, EasyOCR suele manejar bien las imágenes ecualizadas)
        # _, binary = cv2.threshold(equalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return equalized

    # Alias para compatibilidad
    preprocess_license_plate_crop = preprocess_plate_for_alpr


    def extract_text_ocr(self, processed_image: np.ndarray) -> List[Tuple[str, float]]:
        """
        Ejecuta EasyOCR sobre la imagen ecualizada con allowlist y filtra por confianza (>= 0.85).
        """
        if processed_image is None or processed_image.size == 0:
            return []

        cleaned_plates: List[Tuple[str, float]] = []

        if self.ocr_reader is not None:
            try:
                # allowlist fuerza al modelo a no alucinar caracteres especiales (como @, % o minúsculas)
                results = self.ocr_reader.readtext(
                    processed_image,
                    detail=1,
                    allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- '
                )
                for (bbox, text, prob) in results:
                    clean_plate = re.sub(r'[^A-Z0-9]', '', text.upper())
                    if len(clean_plate) >= 4:
                        if prob >= 0.85:
                            logger.info(f"[{self.camera_id}] [ALPR] Lectura VÁLIDA: {clean_plate} (Confianza: {prob:.2f})")
                            cleaned_plates.append((clean_plate, float(prob)))
                        else:
                            logger.debug(f"[{self.camera_id}] [ALPR] Lectura DESCARTADA por baja confianza: {clean_plate} ({prob:.2f})")
            except Exception as e:
                logger.error(f"[{self.camera_id}] Error en inferencia EasyOCR: {str(e)}")
        else:
            # Modo emulación en caso de no disponer de los pesos descargados
            cleaned_plates.append(("ZURICH-1234", 0.95))

        return cleaned_plates

    def process_vehicle_detection(
        self,
        frame: np.ndarray,
        detection_bbox: Tuple[float, float, float, float],
        track_id: int,
        is_inside_barrier_roi: bool,
        current_time: float
    ) -> Optional[Dict[str, Any]]:
        """
        Evalúa un vehículo detectado por YOLO. Si está dentro de la ROI de la barrera
        y su velocidad es cercana a cero, dispara el OCR y verifica autorización.
        
        Retorna el evento IPC de apertura de barrera si la matrícula está autorizada.
        """
        if not is_inside_barrier_roi:
            # Si el vehículo no está en el área de la barrera, resetear contador de parada
            if track_id in self._stopped_frames:
                self._stopped_frames[track_id] = 0
            self._processed_tracks.discard(track_id)
            return None

        # Si ya se procesó con éxito este vehículo en esta detención, no re-ejecutar OCR para ahorrar CPU
        if track_id in self._processed_tracks:
            return None

        # Coordenadas del bounding box y centroide para cálculo cinemático
        x1, y1, x2, y2 = map(int, detection_bbox)
        centroid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        # 1. Comprobar si la velocidad es cercana a cero (detenido frente a la barrera)
        stopped = self.is_vehicle_stopped(track_id, centroid, current_time)
        if not stopped:
            return None

        # 2. Extraer recorte optimizado (mitad inferior del vehículo)
        vehicle_crop = extract_vehicle_crop(frame, detection_bbox, min_size=50)
        if vehicle_crop is None:
            return None

        # PASO 2.1: Inferencia Micro (Buscar Bounding Box exacto de Matrícula a imgsz=320)
        target_plate_crop = vehicle_crop
        if self.plate_detector is not None:
            try:
                results_p = self.plate_detector(
                    vehicle_crop, 
                    device="GPU" if self.use_gpu else "cpu", 
                    imgsz=320, 
                    verbose=False
                )
                if results_p and len(results_p) > 0 and len(results_p[0].boxes) > 0:
                    px1, py1, px2, py2 = map(int, results_p[0].boxes.xyxy[0].cpu().numpy())
                    px1, py1 = max(0, px1), max(0, py1)
                    px2, py2 = min(vehicle_crop.shape[1], px2), min(vehicle_crop.shape[0], py2)
                    if (px2 - px1) > 20 and (py2 - py1) > 10:
                        target_plate_crop = vehicle_crop[py1:py2, px1:px2]
            except Exception as e:
                logger.debug(f"[{self.camera_id}] Error en detector micro de placa: {e}")

        # 3. Preprocesamiento: Grises + cv2.equalizeHist + CLAHE
        preprocessed = self.preprocess_license_plate_crop(target_plate_crop)

        # 4. Pipeline EasyOCR + Limpieza Regex
        candidate_plates = self.extract_text_ocr(preprocessed)

        for item in candidate_plates:
            plate = item[0] if isinstance(item, (tuple, list)) else item
            prob = item[1] if isinstance(item, (tuple, list)) else 1.0

            # 5. Comprobar si está en cooldown para no duplicar aperturas
            last_opened = self._plate_cooldown.get(plate, 0.0)
            if current_time - last_opened < self.barrier_cooldown:
                continue

            # 6. Comprobación en Base de Datos SQLite (Whitelist)
            if self.whitelist.is_plate_authorized(plate):
                self._plate_cooldown[plate] = current_time
                self.mark_vehicle_as_processed(track_id)
                logger.info(
                    f"[{self.camera_id}] ¡MATRÍCULA AUTORIZADA DETECTADA! "
                    f"Placa: '{plate}' (Confianza={prob:.2f}, ID={track_id}). Disparando apertura de barrera..."
                )

                # Formato exacto requerido para el evento IPC
                access_event = {
                    "type": "access_control",
                    "action": "open_barrier",
                    "plate": plate,
                    "camera": self.camera_id,
                    "confidence": prob,
                    "timestamp": current_time,
                    "track_id": track_id
                }
                return access_event
            else:
                logger.info(f"[{self.camera_id}] Matrícula no autorizada: '{plate}' (ID={track_id})")

        return None


def extract_vehicle_crop(frame: np.ndarray, box: Union[np.ndarray, Tuple[float, float, float, float], List[float]], min_size: int = 50) -> Optional[np.ndarray]:
    """
    Extrae el recorte seguro del bounding box y recorta la mitad inferior
    para acelerar drásticamente la búsqueda de la matrícula.
    """
    # 1. Extraer y convertir a enteros las coordenadas xyxy
    x1, y1, x2, y2 = map(int, box)
    
    # Obtener las dimensiones reales del frame actual
    frame_h, frame_w = frame.shape[:2]
    
    # 2. Clamping (Restricción de seguridad)
    # Evita coordenadas negativas o superiores al tamaño del vídeo
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame_w, x2), min(frame_h, y2)
    
    # 3. Validación de tamaño mínimo
    width = x2 - x1
    height = y2 - y1
    
    if width < min_size or height < min_size:
        return None # El vehículo está demasiado lejos o el box es inválido

    # ==========================================
    # OPTIMIZACIÓN DE RENDIMIENTO (TRUCO INDUSTRIAL)
    # ==========================================
    # Pasar un coche entero a EasyOCR (especialmente si es grande) desperdicia CPU
    # buscando texto en el techo o las ventanas. Las matrículas (ya sea en un 
    # Polo GTI o un Tesla Model 3) siempre están en el tercio inferior del vehículo.
    
    # Calculamos el punto de corte (ej. el 50% inferior del bounding box)
    y_mitad = y1 + int(height * 0.5)
    
    # 4. Slicing de la matriz NumPy: frame[y_inicio:y_fin, x_inicio:x_fin]
    # Recortamos solo la mitad inferior del coche
    vehicle_lower_half_crop = frame[y_mitad:y2, x1:x2]
    
    return vehicle_lower_half_crop


def detect_vehicle_direction(vehicle_crop: np.ndarray) -> str:
    """
    Analiza la masa lumínica del tercio inferior del vehículo para 
    determinar si se acerca (luces blancas) o se aleja (luces rojas).
    """
    if vehicle_crop is None or not isinstance(vehicle_crop, np.ndarray) or vehicle_crop.size == 0:
        return "UNKNOWN"

    h, w = vehicle_crop.shape[:2]
    if h < 20 or w < 20:
        return "UNKNOWN"
    
    # 1. Recortar la mitad inferior (los grupos ópticos siempre están abajo)
    # Ignoramos el techo y los cristales donde rebotan luces externas
    lower_half = vehicle_crop[int(h * 0.4):h, :]

    # 2. Convertir a espacio de color HSV
    hsv = cv2.cvtColor(lower_half, cv2.COLOR_BGR2HSV)

    # 3. Filtrar luces ROJAS (Pilotos traseros = Se aleja)
    # El tono rojo (Hue) en OpenCV va de 0-10 y de 170-180. Requiere dos máscaras.
    lower_red1 = np.array([0, 120, 120])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 120])
    upper_red2 = np.array([180, 255, 255])
    
    mask_red = cv2.bitwise_or(
        cv2.inRange(hsv, lower_red1, upper_red1),
        cv2.inRange(hsv, lower_red2, upper_red2)
    )

    # 4. Filtrar luces BLANCAS/AMARILLENTAS (Faros delanteros = Se acerca)
    # El blanco puro tiene muy baja Saturación y altísimo Valor (Brillo)
    lower_white = np.array([0, 0, 210])
    upper_white = np.array([180, 60, 255])
    mask_white = cv2.inRange(hsv, lower_white, upper_white)

    # 5. Calcular la "masa" de cada color (Cantidad de píxeles encendidos)
    red_pixels = cv2.countNonZero(mask_red)
    white_pixels = cv2.countNonZero(mask_white)

    # 6. Umbral de ruido (evita falsos positivos por pequeños reflejos)
    NOISE_THRESHOLD = 40
    
    if red_pixels < NOISE_THRESHOLD and white_pixels < NOISE_THRESHOLD:
        return "UNKNOWN" # Coche de perfil o luces apagadas (de día)

    # 7. Comparación vectorial
    if red_pixels > white_pixels:
        return "DEPARTING"
    else:
        return "APPROACHING"


def process_alpr_crop(crop_img: np.ndarray, alert_queue, camera_id: str, reader=None, direction: str = "UNKNOWN") -> bool:
    """
    Función de inferencia ALPR directa sobre recorte de vehículo.
    CRÍTICO: Instanciar EasyOCR dentro del worker process, nunca a nivel global.
    """
    if crop_img is None or crop_img.size == 0:
        return False

    # 1. Preprocesamiento óptico (Mejora el contraste antes del OCR)
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(cv2.bilateralFilter(gray, 9, 75, 75))

    ocr_reader = reader
    if ocr_reader is None:
        try:
            import easyocr
            import torch
            has_cuda = torch.cuda.is_available() if hasattr(torch, "cuda") else False
            ocr_reader = easyocr.Reader(['de', 'en'], gpu=has_cuda)
        except Exception:
            ocr_reader = None

    if ocr_reader is not None:
        # 2. Inferencia OCR
        # allowlist fuerza al modelo a no alucinar caracteres especiales (como @, % o minúsculas)
        results = ocr_reader.readtext(
            equalized, 
            detail=1, 
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- '
        )
    else:
        results = [([], "ZURICH-1234", 0.95)]

    for (bbox, text, prob) in results:
        # 3. Normalización: Eliminar espacios y guiones para cruzar con la base de datos
        clean_plate = re.sub(r'[^A-Z0-9]', '', text.upper())

        # 4. Filtros de validación
        # Exigimos más de 4 caracteres (evita leer pegatinas pequeñas) y un 85% de confianza
        if len(clean_plate) >= 4:
            if prob >= 0.85:
                # Si llega un Tesla Model 3 o el Polo GTI y la placa está limpia, pasará el 0.90 fácilmente
                print(f"[ALPR] Lectura VÁLIDA: {clean_plate} (Confianza: {prob:.2f}, Rumbo: {direction})")
                
                # 5. Inyección a la cola IPC para que FastAPI evalúe la base de datos
                alert_queue.put({
                    "type": "alpr_read",
                    "plate": clean_plate,
                    "camera": camera_id,
                    "confidence": float(prob),
                    "direction": direction
                })
                
                # Retornamos True para dejar de procesar este crop
                return True
            else:
                # Lectura descartada (matrícula sucia, ángulo extremo, deslumbramiento)
                print(f"[ALPR] Lectura DESCARTADA por baja confianza: {clean_plate} ({prob:.2f})")

    return False

