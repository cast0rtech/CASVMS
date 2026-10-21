# ==============================================================================
# CASVMS - Camera Worker Subprocess (IPC Isolated Multiprocessing)
# ==============================================================================
import os
import cv2
import time
import math
import logging
from typing import Dict, Any, List, Optional
import multiprocessing as mp
import numpy as np

from core.types import (
    Point2D,
    TrackedDetection,
    TripwireConfig,
    ZoneConfig,
    CrowdConfig,
    AlertEvent,
    TelemetryData,
    RuleType,
    Severity
)
from core.motion import MotionGatekeeper
from core.detector import EdgeYOLODetector
from core.analytics import VectorAnalyticsEngine
from core.dvr import SmartRAMDVR
from core.alpr import ALPRPipeline, VEHICLE_CLASSES

logger = logging.getLogger("CASVMS.CameraWorker")

def generate_synthetic_frame(frame_idx: int, width: int = 1280, height: int = 720) -> np.ndarray:
    """
    Genera un frame sintético de simulación industrial para pruebas zero-config
    cuando no hay una cámara RTSP física conectada.
    """
    # Fondo degradado industrial oscuro
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (24, 28, 34)
    
    # Cuadrícula tenue
    for x in range(0, width, 80):
        cv2.line(frame, (x, 0), (x, height), (35, 40, 48), 1)
    for y in range(0, height, 80):
        cv2.line(frame, (0, y), (width, y), (35, 40, 48), 1)

    # Objeto en movimiento simulado (persona desplazándose periódicamente)
    t = frame_idx * 0.05
    cx = int(width / 2 + math.sin(t) * (width * 0.35))
    cy = int(height / 2 + math.cos(t * 0.7) * (height * 0.25))
    
    # Dibujar cuerpo simulado
    cv2.circle(frame, (cx, cy - 30), 20, (180, 200, 220), -1)
    cv2.rectangle(frame, (cx - 25, cy - 10), (cx + 25, cy + 60), (140, 160, 190), -1)
    
    # Texto de simulación
    cv2.putText(
        frame, "SIMULACION INDUSTRIAL DE PATRULLAJE (RTSP OFFLINE)",
        (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 200, 100), 2
    )
    return frame

def draw_annotations(
    frame: np.ndarray,
    detections: List[TrackedDetection],
    tripwires: List[TripwireConfig],
    zones: List[ZoneConfig],
    in_count: int,
    out_count: int,
    is_standby: bool,
    fps: float,
    cam_name: str,
    active_alpr: Optional[Dict[str, Any]] = None
) -> np.ndarray:
    """
    Renderiza sobre el frame los vectores de analítica (polígonos, tripwires,
    bounding boxes, IDs, telemetría OSD y notificaciones ALPR) para el streaming visual.
    """
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    # 1. Dibujar Zonas Poligonales
    for z in zones:
        if not z.enabled or len(z.polygon) < 3:
            continue
        pts = np.array(z.polygon, dtype=np.int32).reshape((-1, 1, 2))
        
        # Color según tipo: Rojo para intrusión, Amarillo para Dwell/Parking
        color = (0, 0, 220) if z.rule_type == RuleType.INTRUSION else (0, 215, 255)
        
        # Capa semitransparente
        overlay = annotated.copy()
        cv2.fillPoly(overlay, [pts], color)
        cv2.addWeighted(overlay, 0.25, annotated, 0.75, 0, annotated)
        cv2.polylines(annotated, [pts], True, color, 2, cv2.LINE_AA)
        
        # Etiqueta de la zona
        label_pos = (int(z.polygon[0][0]), int(z.polygon[0][1]) - 8)
        cv2.putText(annotated, f"[{z.name}]", label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    # 2. Dibujar Tripwires Direccionales
    for tw in tripwires:
        if not tw.enabled:
            continue
        p1 = (int(tw.pt1[0]), int(tw.pt1[1]))
        p2 = (int(tw.pt2[0]), int(tw.pt2[1]))
        
        # Línea cian con flecha direccional
        cv2.arrowedLine(annotated, p1, p2, (255, 255, 0), 2, cv2.LINE_AA, tipLength=0.08)
        mid_x = int((p1[0] + p2[0]) / 2)
        mid_y = int((p1[1] + p2[1]) / 2) - 8
        cv2.putText(annotated, f"TW: {tw.name}", (mid_x, mid_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)

    # 3. Dibujar Detecciones y Bounding Boxes con IDs
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        fx, fy = int(det.foot_point[0]), int(det.foot_point[1])
        
        box_color = (0, 255, 120) if det.class_name == "person" else (255, 160, 50)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
        
        # Punto de contacto sobre el suelo
        cv2.circle(annotated, (fx, fy), 4, (0, 0, 255), -1)
        
        # Etiqueta con Track ID
        label = f"#{det.track_id} {det.class_name} {det.confidence:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - 20), (x1 + lw, y1), box_color, -1)
        cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    # 4. Banner OSD de Apertura de Barrera ALPR
    if active_alpr and (time.time() - active_alpr.get("timestamp", 0) < 4.0):
        plate = active_alpr.get("plate", "---")
        msg = f">> ACCESO AUTORIZADO: [{plate}] - ABRIENDO BARRERA <<"
        (tw_w, tw_h), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        bar_y1 = h - 70
        bar_y2 = h - 20
        cv2.rectangle(annotated, (w // 2 - tw_w // 2 - 20, bar_y1), (w // 2 + tw_w // 2 + 20, bar_y2), (0, 180, 0), -1)
        cv2.rectangle(annotated, (w // 2 - tw_w // 2 - 20, bar_y1), (w // 2 + tw_w // 2 + 20, bar_y2), (255, 255, 255), 2)
        cv2.putText(annotated, msg, (w // 2 - tw_w // 2, bar_y1 + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    # 5. Banner Superior OSD (Telemetría de la cámara)
    cv2.rectangle(annotated, (0, 0), (w, 40), (15, 18, 22), -1)
    
    status_text = "STANDBY (MOG2)" if is_standby else "ACTIVE (YOLO+OPENVINO)"
    status_color = (160, 160, 160) if is_standby else (0, 255, 0)
    
    osd_str = f"{cam_name} | FPS: {fps:.1f} | IN: {in_count} | OUT: {out_count} | {status_text}"
    cv2.putText(annotated, osd_str, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 1, cv2.LINE_AA)
    cv2.circle(annotated, (w - 25, 20), 8, status_color, -1)

    return annotated


def run_camera_process(
    camera_id: str,
    camera_name: str,
    rtsp_url: str,
    rules_dict: Dict[str, Any],
    shared_frames: Any,        # multiprocessing.Manager().dict()
    event_queue: mp.Queue,     # multiprocessing.Queue()
    stop_event: mp.Event,      # multiprocessing.Event()
    reset_event: mp.Event,     # multiprocessing.Event()
    device: str = "GPU"
) -> None:
    """
    Función de entrada del proceso aislado de cada cámara.
    Inicializa sus propios modelos de inferencia, gateways analíticos y búfer DVR.
    """
    logger.info(f"[{camera_id}] Proceso de cámara iniciado (PID: {os.getpid()}).")
    
    # 1. Instanciación aislada de componentes de IA
    gatekeeper = MotionGatekeeper(analysis_width=640, analysis_height=360)
    
    # El objeto YOLO NO puede compartirse entre procesos. Se inicializa aquí:
    detector = EdgeYOLODetector(device=device)
    analytics = VectorAnalyticsEngine(camera_id=camera_id)
    dvr = SmartRAMDVR(camera_id=camera_id, fps=15.0)

    # CRÍTICO: EasyOCR instanciado DENTRO del worker (no globalmente) para evitar colisiones IPC
    alpr_pipeline = ALPRPipeline(camera_id=camera_id, use_gpu=False)
    active_alpr_event: Optional[Dict[str, Any]] = None

    # Decodificación de reglas iniciales
    tripwires: List[TripwireConfig] = [
        TripwireConfig(**tw) for tw in rules_dict.get("tripwires", [])
    ]
    zones: List[ZoneConfig] = [
        ZoneConfig(**z) for z in rules_dict.get("zones", [])
    ]
    crowd_cfg = CrowdConfig(**rules_dict.get("crowd", {})) if "crowd" in rules_dict else None

    # Inicialización de captura de vídeo
    is_simulation = rtsp_url.lower() in ["demo", "sim", "none", ""]
    cap = None
    if not is_simulation:
        logger.info(f"[{camera_id}] Conectando a stream RTSP: {rtsp_url}...")
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        # Ajustes de buffer RTSP para latencia mínima
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    frame_counter = 0
    fps_start_time = time.time()
    current_fps = 0.0
    last_telemetry_emit = 0.0

    while not stop_event.is_set():
        loop_start = time.time()

        # Comprobar evento de reset de aforo (ej. disparado por el Cron de medianoche)
        if reset_event.is_set():
            analytics.reset_counts()
            reset_event.clear()
            logger.info(f"[{camera_id}] Evento de reset de aforo ejecutado en proceso hijo.")

        # Obtención del fotograma
        frame = None
        if cap and cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning(f"[{camera_id}] Pérdida de señal RTSP. Reintentando...")
                time.sleep(1.0)
                continue
        else:
            # Modo demostración / simulación activa
            frame = generate_synthetic_frame(frame_counter)

        frame_counter += 1
        now = time.time()

        # 1. Gatekeeper MOG2 (Detección de Movimiento & Standby)
        raw_motion, is_standby, motion_area, _ = gatekeeper.evaluate(frame)

        detections: List[TrackedDetection] = []

        # 2. Inferencia YOLOv8 + ByteTrack (Únicamente si NO está en standby)
        if not is_standby:
            detections = detector.track(frame)
        
        # 3. Motor Analítico Vectorial
        tw_alerts = analytics.process_tripwires(detections, tripwires, now)
        zone_alerts = analytics.process_zones(detections, zones, now)
        crowd_alerts = analytics.process_crowd(detections, crowd_cfg, now)
        
        all_alerts = tw_alerts + zone_alerts + crowd_alerts
        for alert in all_alerts:
            # Enviar evento a la cola IPC hacia el proceso principal
            event_queue.put(alert)
            # Activar grabación en RAM DVR
            dvr.trigger_incident(alert.alert_id, alert.rule_id, alert.metadata)

        # 3.1 Pipeline ALPR: Reconocimiento Automático de Matrículas en Zona de Entrada / Barrera
        for det in detections:
            if det.class_name in VEHICLE_CLASSES and det.track_id >= 0:
                # Comprobar si el vehículo se encuentra dentro de la zona de entrada/parking
                is_inside_roi = False
                if len(zones) > 0:
                    for z in zones:
                        if len(z.polygon) >= 3:
                            pts = np.array(z.polygon, dtype=np.float32).reshape((-1, 1, 2))
                            fx, fy = det.foot_point
                            if cv2.pointPolygonTest(pts, (float(fx), float(fy)), False) >= 0:
                                is_inside_roi = True
                                break
                else:
                    # En ausencia de polígonos explícitos, evaluar en todo el encuadre
                    is_inside_roi = True

                access_event = alpr_pipeline.process_vehicle_detection(
                    frame=frame,
                    detection_bbox=det.bbox,
                    track_id=det.track_id,
                    is_inside_barrier_roi=is_inside_roi,
                    current_time=now
                )

                if access_event:
                    # Inyección del evento en la cola IPC
                    event_queue.put(access_event)
                    active_alpr_event = access_event

                    # Disparar grabación en RAM DVR del evento de acceso
                    dvr.trigger_incident(
                        alert_id=f"alpr_{access_event['plate']}_{int(now)}",
                        rule_name=f"ACCESO_BARRERA_{access_event['plate']}",
                        metadata=access_event
                    )

        # Actualizar memoria de tracking
        analytics.update_tracks(detections, now)

        # 4. Almacenar en búfer circular Smart DVR
        dvr.push_frame(frame, now)

        # 5. Cálculo de FPS
        if frame_counter % 15 == 0:
            elapsed = time.time() - fps_start_time
            current_fps = 15.0 / max(0.001, elapsed)
            fps_start_time = time.time()

        # 6. Emisión periódica de Telemetría cada 1 segundo
        if now - last_telemetry_emit >= 1.0:
            active_occupancy = max(0, analytics.in_count - analytics.out_count)
            telemetry = TelemetryData(
                camera_id=camera_id,
                timestamp=now,
                in_count=analytics.in_count,
                out_count=analytics.out_count,
                active_occupancy=active_occupancy,
                active_tracks=len(detections),
                fps=round(current_fps, 1),
                motion_detected=raw_motion,
                is_standby=is_standby
            )
            event_queue.put(telemetry)
            last_telemetry_emit = now

        # 7. Renderizado de anotaciones y compresión JPEG para Streaming MJPEG
        annotated_frame = draw_annotations(
            frame=frame,
            detections=detections,
            tripwires=tripwires,
            zones=zones,
            in_count=analytics.in_count,
            out_count=analytics.out_count,
            is_standby=is_standby,
            fps=current_fps,
            cam_name=camera_name,
            active_alpr=active_alpr_event
        )

        encode_ok, jpeg_bytes = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if encode_ok:
            # Actualizar diccionario compartido IPC (Manager.dict)
            shared_frames[camera_id] = jpeg_bytes.tobytes()

        # Control de cadencia de frames (~20-25 FPS para no saturar bus en simulación)

        cycle_duration = time.time() - loop_start
        target_duration = 1.0 / 20.0
        if cycle_duration < target_duration:
            time.sleep(target_duration - cycle_duration)

    if cap:
        cap.release()
    logger.info(f"[{camera_id}] Proceso de cámara finalizado limpiamente.")
