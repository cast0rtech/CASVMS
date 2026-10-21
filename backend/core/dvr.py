# ==============================================================================
# CASVMS - Smart RAM Circular DVR (Real-time JPEG Compression & Clip Stitcher)
# ==============================================================================
import os
import cv2
import time
import json
import logging
import threading
import subprocess
from collections import deque
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

logger = logging.getLogger("CASVMS.SmartDVR")

class SmartRAMDVR:
    """
    Grabador de vídeo digital (DVR) inteligente en memoria RAM.
    
    Mantiene un búfer circular (deque) de fotogramas comprimidos a JPEG en tiempo real.
    Al detectarse una alarma:
    1. Congela los N minutos previos de vídeo (Pre-event buffer).
    2. Continúa almacenando los N minutos posteriores (Post-event buffer).
    3. Delega a un Hilo en Background la decodificación y ensamblado hacia un archivo .mp4,
       garantizando que el proceso de captura de vídeo no experimente contención de I/O.
    """

    def __init__(
        self,
        camera_id: str,
        storage_dir: str = "/app/storage/recordings",
        fps: float = 15.0,
        pre_event_seconds: int = 300,   # 5 minutos pre-alerta
        post_event_seconds: int = 300,  # 5 minutos post-alerta
        jpeg_quality: int = 75          # Calidad de compresión visual/memoria óptima
    ):
        self.camera_id = camera_id
        self.storage_dir = storage_dir
        self.fps = max(1.0, fps)
        self.pre_event_seconds = pre_event_seconds
        self.post_event_seconds = post_event_seconds
        self.jpeg_quality = jpeg_quality
        
        # Parámetros de codificación JPEG
        self._encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        
        # Cálculo del tamaño máximo del búfer circular
        self.pre_event_capacity = int(self.pre_event_seconds * self.fps)
        self.post_event_capacity = int(self.post_event_seconds * self.fps)
        
        # Búfer circular en RAM: almacena tuplas (timestamp: float, jpeg_bytes: bytes)
        self._pre_buffer: deque = deque(maxlen=self.pre_event_capacity)
        self._buffer_lock = threading.Lock()
        
        # Estado de grabación post-evento activa
        self._is_recording_incident = False
        self._post_buffer: List[Tuple[float, bytes]] = []
        self._active_incident_meta: Dict[str, Any] = {}
        self._post_frames_remaining = 0
        
        # Asegurar existencia del directorio de almacenamiento
        os.makedirs(self.storage_dir, exist_ok=True)
        
        logger.info(
            f"SmartDVR inicializado para '{camera_id}'. Búfer circular pre-evento: "
            f"{self.pre_event_capacity} frames (~{self.pre_event_seconds}s @ {self.fps} FPS)."
        )

    def push_frame(self, frame: np.ndarray, timestamp: Optional[float] = None) -> None:
        """
        Comprime el frame entrante a JPEG en RAM y actualiza el búfer circular.
        Si hay un incidente activo, acumula frames en el búfer post-evento.
        """
        if frame is None or frame.size == 0:
            return

        ts = timestamp or time.time()

        try:
            # 1. Compresión en tiempo real a JPEG para mitigar consumo de RAM
            success, enc_frame = cv2.imencode(".jpg", frame, self._encode_param)
            if not success:
                logger.warning(f"Fallo al codificar frame JPEG en cámara '{self.camera_id}'.")
                return

            frame_bytes = enc_frame.tobytes()

            with self._buffer_lock:
                # Actualizar búfer circular constante
                self._pre_buffer.append((ts, frame_bytes))

                # Manejar grabación activa de post-evento
                if self._is_recording_incident:
                    self._post_buffer.append((ts, frame_bytes))
                    self._post_frames_remaining -= 1

                    if self._post_frames_remaining <= 0:
                        # Periodo post-alerta completado: disparar hilo de exportación
                        logger.info(
                            f"[{self.camera_id}] Grabación post-evento finalizada. "
                            f"Iniciando empaquetado de {len(self._pre_buffer) + len(self._post_buffer)} frames a MP4..."
                        )
                        self._trigger_async_stitch()

        except Exception as e:
            logger.error(f"Error procesando frame en SmartDVR: {str(e)}", exc_info=True)

    def trigger_incident(self, alert_id: str, rule_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Dispara la captura de un clip de incidente (Pre-alerta + Post-alerta).
        Si ya existía un incidente activo, prorroga la ventana de grabación.
        """
        with self._buffer_lock:
            if not self._is_recording_incident:
                self._is_recording_incident = True
                self._post_frames_remaining = self.post_event_capacity
                self._post_buffer = []
                self._active_incident_meta = {
                    "alert_id": alert_id,
                    "camera_id": self.camera_id,
                    "rule_name": rule_name,
                    "trigger_timestamp": time.time(),
                    "metadata": metadata or {},
                    "pre_frames_frozen": list(self._pre_buffer)  # Snapshot inmutable de los 5 min previos
                }
                logger.warning(
                    f"[{self.camera_id}] Alarma registrada! SmartDVR activo: "
                    f"Guardando {self.post_event_seconds}s adicionales..."
                )
            else:
                # Si llega otra alarma durante la grabación, renovar la ventana post-evento
                self._post_frames_remaining = self.post_event_capacity
                logger.info(f"[{self.camera_id}] Alerta recurrente: ventana de grabación post-evento prorrogada.")

    def _trigger_async_stitch(self) -> None:
        """Extrae los frames congelados y delega la renderización a un hilo demonio."""
        pre_frames = self._active_incident_meta.get("pre_frames_frozen", [])
        post_frames = list(self._post_buffer)
        meta = dict(self._active_incident_meta)
        
        # Resetear estado de captura
        self._is_recording_incident = False
        self._post_buffer = []
        self._active_incident_meta = {}

        # Ejecutar en hilo de fondo para no bloquear la captura de vídeo
        stitch_thread = threading.Thread(
            target=self._stitch_and_export_worker,
            args=(pre_frames, post_frames, meta),
            daemon=True,
            name=f"SmartDVR-Export-{self.camera_id}"
        )
        stitch_thread.start()

    def _stitch_and_export_worker(
        self,
        pre_frames: List[Tuple[float, bytes]],
        post_frames: List[Tuple[float, bytes]],
        metadata: Dict[str, Any]
    ) -> None:
        """
        Hilo de fondo: Descomprime los frames JPEG y escribe un contenedor MP4 estandarizado.
        """
        all_frames = pre_frames + post_frames
        total_count = len(all_frames)
        
        if total_count == 0:
            logger.warning(f"[{self.camera_id}] Intento de exportar clip sin frames.")
            return

        t_trigger = metadata.get("trigger_timestamp", time.time())
        formatted_date = time.strftime("%Y%m%d_%H%M%S", time.localtime(t_trigger))
        alert_id = metadata.get("alert_id", "incident")[:8]
        filename = f"{self.camera_id}_{formatted_date}_{alert_id}.mp4"
        output_filepath = os.path.join(self.storage_dir, filename)
        meta_filepath = os.path.join(self.storage_dir, f"{filename}.json")

        logger.info(f"[{self.camera_id}] Iniciando exportación de vídeo: {output_filepath} ({total_count} frames)...")

        writer = None
        start_stitch_time = time.time()

        try:
            # 1. Decodificar el primer frame para determinar resolución
            first_ts, first_jpeg = all_frames[0]
            first_img = cv2.imdecode(np.frombuffer(first_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            if first_img is None:
                raise ValueError("No se pudo decodificar el primer frame de la secuencia JPEG.")

            height, width = first_img.shape[:2]
            
            # 2. Configurar VideoWriter con FourCC 'mp4v' (compatible multiplataforma nativo)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_filepath, fourcc, self.fps, (width, height))

            if not writer.isOpened():
                raise RuntimeError(f"No se pudo inicializar VideoWriter para la ruta: {output_filepath}")

            # Escribir el primer frame
            writer.write(first_img)

            # 3. Decodificar y empalmar el resto de frames secuencialmente
            for idx, (ts, jpeg_data) in enumerate(all_frames[1:], start=2):
                img = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    writer.write(img)
                if idx % 500 == 0:
                    logger.debug(f"[{self.camera_id}] Progreso renderizado MP4: {idx}/{total_count} frames...")

            writer.release()
            writer = None

            elapsed = time.time() - start_stitch_time
            file_size_mb = os.path.getsize(output_filepath) / (1024 * 1024)

            # 4. Guardar archivo de metadatos del clip
            clip_meta = {
                "filename": filename,
                "filepath": output_filepath,
                "camera_id": self.camera_id,
                "alert_id": metadata.get("alert_id"),
                "rule_name": metadata.get("rule_name"),
                "total_frames": total_count,
                "duration_seconds": total_count / self.fps,
                "fps": self.fps,
                "resolution": f"{width}x{height}",
                "size_mb": round(file_size_mb, 2),
                "export_time_seconds": round(elapsed, 2),
                "created_at": time.time(),
                "metadata": metadata.get("metadata", {})
            }

            with open(meta_filepath, "w", encoding="utf-8") as f:
                json.dump(clip_meta, f, indent=2)

            logger.info(
                f"[{self.camera_id}] Clip MP4 generado con éxito: '{filename}' "
                f"({clip_meta['duration_seconds']:.1f}s, {file_size_mb:.2f} MB en {elapsed:.1f}s)."
            )

        except Exception as e:
            logger.error(f"Error crítico en hilo de renderizado MP4 de SmartDVR: {str(e)}", exc_info=True)
            if writer is not None:
                writer.release()
