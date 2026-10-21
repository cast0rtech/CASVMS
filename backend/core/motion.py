# ==============================================================================
# CASVMS - Gatekeeper MOG2 (Motion Detection & Standby Controller)
# ==============================================================================
import cv2
import numpy as np
import logging
from typing import Tuple, Optional

logger = logging.getLogger("CASVMS.Gatekeeper")

class MotionGatekeeper:
    """
    Subtractor de fondo MOG2 optimizado para Edge AI.
    
    Analiza frames reducidos a 640x360 para determinar si existe actividad cinemática
    en la escena antes de invocar la red neuronal profunda (YOLOv8).
    Incorpora un mecanismo de histéresis (cooldown) para evitar conmutaciones
    frecuentes entre modo activo y standby.
    """
    
    def __init__(
        self,
        analysis_width: int = 640,
        analysis_height: int = 360,
        history: int = 300,
        var_threshold: float = 32.0,
        detect_shadows: bool = True,
        min_motion_area_px: int = 1200,      # Píxeles de movimiento en resolución 640x360 (~0.5%)
        standby_cooldown_frames: int = 45    # ~1.5 - 2 segundos a 25-30 FPS antes de entrar en standby
    ):
        self.width = analysis_width
        self.height = analysis_height
        self.min_motion_area = min_motion_area_px
        self.standby_cooldown = standby_cooldown_frames
        
        # Histéresis interna
        self._cooldown_counter = 0
        self._is_standby = True
        
        # Inicialización del algoritmo MOG2
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows
        )
        
        # Elemento estructurante para operaciones morfológicas (filtrado de ruido y sombras)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        
        logger.info(
            f"Gatekeeper MOG2 inicializado. Escala: {self.width}x{self.height}, "
            f"Umbral área: {self.min_motion_area}px, Cooldown: {self.standby_cooldown} frames."
        )

    def evaluate(self, frame: np.ndarray) -> Tuple[bool, bool, float, Optional[np.ndarray]]:
        """
        Evalúa el frame actual para detectar movimiento.
        
        Args:
            frame: Imagen BGR de entrada (resolución nativa de la cámara).
            
        Returns:
            Tuple[bool, bool, float, Optional[np.ndarray]]:
                - motion_detected: True si hay cambio de píxeles en el frame actual.
                - is_standby: True si el sistema debe permanecer en standby (sin YOLO).
                - motion_area: Área total de píxeles en movimiento detectados.
                - fg_mask: Máscara binaria del movimiento procesado.
        """
        try:
            if frame is None or frame.size == 0:
                return False, True, 0.0, None

            # 1. Reducción de escala para aligerar procesamiento en CPU
            resized = cv2.resize(
                frame, 
                (self.width, self.height), 
                interpolation=cv2.INTER_AREA
            )
            
            # 2. Suavizado gaussiano para atenuar ruido de sensor y artefactos de compresión RTSP
            blurred = cv2.GaussianBlur(resized, (5, 5), 0)
            
            # 3. Aplicación del sustractor MOG2
            # El valor 127 corresponde a sombras si detectShadows=True, 255 es primer plano real
            raw_mask = self._subtractor.apply(blurred)
            
            # 4. Binarización estricta para eliminar sombras proyectadas (degradan la precisión)
            _, thresh_mask = cv2.threshold(raw_mask, 250, 255, cv2.THRESH_BINARY)
            
            # 5. Operación morfológica de apertura y cierre para consolidar blobs reales
            clean_mask = cv2.morphologyEx(thresh_mask, cv2.MORPH_OPEN, self._kernel)
            clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_DILATE, self._kernel)
            
            # 6. Conteo de píxeles no nulos
            motion_pixels = float(cv2.countNonZero(clean_mask))
            raw_motion = motion_pixels >= self.min_motion_area
            
            # 7. Lógica de histéresis y control de Standby
            if raw_motion:
                self._cooldown_counter = self.standby_cooldown
                self._is_standby = False
            else:
                if self._cooldown_counter > 0:
                    self._cooldown_counter -= 1
                    self._is_standby = False
                else:
                    self._is_standby = True
                    
            return raw_motion, self._is_standby, motion_pixels, clean_mask

        except Exception as e:
            logger.error(f"Error evaluando Gatekeeper MOG2: {str(e)}", exc_info=True)
            # En caso de excepción, mantener activo para garantizar seguridad operativa
            return True, False, 0.0, None

    def reset(self) -> None:
        """Reinicia el estado del sustractor de fondo y contadores."""
        self._cooldown_counter = 0
        self._is_standby = True
        logger.debug("Gatekeeper MOG2 reiniciado.")
