# ==============================================================================
# CASVMS - Main FastAPI Orchestrator & Edge Engine
# ==============================================================================
import os
import glob
import json
import time
import asyncio
import logging
import multiprocessing as mp
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from core.types import (
    AlertEvent,
    TelemetryData,
    TripwireConfig,
    ZoneConfig,
    RuleType,
    Severity
)
from gateways import (
    InfluxTelemetryGateway,
    MQTTIndustrialGateway,
    ModbusIndustrialGateway,
    MidnightResetCron
)
from engine.camera_process import run_camera_process

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("CASVMS.Main")

# ==============================================================================
# ESTADO GLOBAL Y SINCRONIZACIÓN IPC
# ==============================================================================
mp_manager = mp.Manager()
shared_frames = mp_manager.dict()
event_queue = mp.Queue()

# Contenedores de procesos
camera_processes: Dict[str, mp.Process] = {}
camera_stop_events: Dict[str, mp.Event] = {}
camera_reset_events: List[mp.Event] = []

# Gateways industriales
influx_gw: Optional[InfluxTelemetryGateway] = None
mqtt_gw: Optional[MQTTIndustrialGateway] = None
modbus_gw: Optional[ModbusIndustrialGateway] = None
midnight_cron: Optional[MidnightResetCron] = None
onvif_scheduler: Any = None


# Colas de difusión para Server-Sent Events (SSE)
sse_subscribers: List[asyncio.Queue] = []

# Caché de telemetría y configuración en memoria
telemetry_cache: Dict[str, Dict[str, Any]] = {}
recent_alerts: List[Dict[str, Any]] = []

# Directorio de grabaciones
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "/app/storage/recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

from core.config_manager import (
    load_cameras_config,
    save_cameras_config,
    load_modbus_config,
    save_modbus_config
)
from core.onvif_discovery import discover_onvif_devices, test_rtsp_connection

def start_camera_worker(cam_cfg: Dict[str, Any], device: str) -> bool:
    """Inicia de forma aislada el proceso de inferencia y streaming de una cámara."""
    cam_id = cam_cfg["id"]
    if not cam_cfg.get("enabled", True):
        logger.info(f"Cámara '{cam_id}' deshabilitada en configuración. No se inicia proceso.")
        return False

    stop_camera_worker(cam_id)
    stop_evt = mp.Event()
    reset_evt = mp.Event()
    
    camera_stop_events[cam_id] = stop_evt
    camera_reset_events.append(reset_evt)

    proc = mp.Process(
        target=run_camera_process,
        args=(
            cam_id,
            cam_cfg.get("name", cam_id),
            cam_cfg.get("rtsp_url", "demo"),
            cam_cfg.get("rules", {}),
            shared_frames,
            event_queue,
            stop_evt,
            reset_evt,
            device
        ),
        daemon=True,
        name=f"Worker-{cam_id}"
    )
    proc.start()
    camera_processes[cam_id] = proc
    logger.info(f"Cámara '{cam_id}' iniciada con PID={proc.pid}.")
    return True

def stop_camera_worker(cam_id: str):
    """Detiene y limpia el proceso worker de una cámara."""
    if cam_id in camera_stop_events:
        try:
            camera_stop_events[cam_id].set()
        except Exception:
            pass
    if cam_id in camera_processes:
        proc = camera_processes.pop(cam_id, None)
        if proc and proc.is_alive():
            proc.join(timeout=1.5)
            if proc.is_alive():
                proc.terminate()
        logger.info(f"Worker de cámara '{cam_id}' detenido.")
    camera_stop_events.pop(cam_id, None)



# ==============================================================================
# HILO CONSUMIDOR DE EVENTOS IPC Y DESPACHO A GATEWAYS
# ==============================================================================
def event_dispatcher_worker(
    queue: mp.Queue,
    loop: asyncio.AbstractEventLoop
):
    """
    Lee continuamente los eventos emitidos por los procesos hijos y los despacha
    a InfluxDB, MQTT, Modbus TCP y la cola de difusión SSE para el frontend.
    """
    logger.info("Despachador de eventos IPC iniciado.")
    while True:
        try:
            item = queue.get()
            if item is None:
                break

            if isinstance(item, AlertEvent):
                # 1. Despacho a MQTT (Tópico jerárquico)
                if mqtt_gw:
                    mqtt_gw.publish_alert(item)

                # 2. Despacho a Modbus (Activar bandera de intrusión si aplica)
                if modbus_gw and item.rule_type == RuleType.INTRUSION:
                    modbus_gw.set_intrusion_alarm(True)

                # 3. Guardar en historial en memoria
                alert_dict = {
                    "alert_id": item.alert_id,
                    "camera_id": item.camera_id,
                    "rule_id": item.rule_id,
                    "rule_type": item.rule_type.value,
                    "severity": item.severity.value,
                    "timestamp": item.timestamp,
                    "message": item.message,
                    "metadata": item.metadata
                }
                recent_alerts.insert(0, alert_dict)
                if len(recent_alerts) > 100:
                    recent_alerts.pop()

                # 4. Difusión asíncrona a clientes SSE
                for sub_queue in list(sse_subscribers):
                    try:
                        loop.call_soon_threadsafe(sub_queue.put_nowait, alert_dict)
                    except Exception:
                        pass

            elif isinstance(item, dict) and item.get("type") == "alpr_read":
                # Interceptar evento de lectura de matrícula OCR
                scanned_plate = item.get("plate", "")
                cam_id = item.get("camera", "cam_parking")
                
                from core.plate_whitelist import ALPRWhitelistDB
                alpr_db = ALPRWhitelistDB()
                access_info = alpr_db.check_access(scanned_plate)
                
                if access_info:
                    owner_name = access_info.get("owner", "Autorizado")
                    logger.info(f"[ALPR] Acceso AUTORIZADO: {scanned_plate} ({owner_name})")
                    
                    # 1. Disparar PLC vía Modbus (Coil 0 por defecto)
                    try:
                        from gateways.barrier_gateway import ModbusBarrierGateway
                        barrier_gw = ModbusBarrierGateway()
                        barrier_coil = int(os.getenv("PLC_BARRIER_COIL", "0"))
                        barrier_gw.trigger_barrier(coil_address=barrier_coil)
                    except Exception as plc_err:
                        logger.error(f"[ALPR] Error accionando barrera PLC: {plc_err}")
                        
                    # 2. Notificación al frontend (Panel SSE) y MQTT
                    notif_event = {
                        "alert_id": f"alpr_auth_{scanned_plate}_{int(time.time())}",
                        "camera_id": cam_id,
                        "rule_id": "rule_alpr_barrier",
                        "rule_type": "access_control",
                        "severity": "info",
                        "timestamp": item.get("timestamp", time.time()),
                        "message": f"Barrera abierta para {owner_name} [{scanned_plate}]",
                        "metadata": {"plate": scanned_plate, "owner": owner_name, "authorized": True}
                    }
                    recent_alerts.insert(0, notif_event)
                    if len(recent_alerts) > 100:
                        recent_alerts.pop()
                    if mqtt_gw:
                        mqtt_gw.client.publish(f"vms/cameras/{cam_id}/access_control", json.dumps(notif_event), qos=1)
                    for sub_queue in list(sse_subscribers):
                        try:
                            loop.call_soon_threadsafe(sub_queue.put_nowait, notif_event)
                        except Exception:
                            pass
                else:
                    logger.warning(f"[ALPR] Acceso DENEGADO: {scanned_plate}")
                    denied_event = {
                        "alert_id": f"alpr_denied_{scanned_plate}_{int(time.time())}",
                        "camera_id": cam_id,
                        "rule_id": "rule_alpr_barrier",
                        "rule_type": "access_control",
                        "severity": "high",
                        "timestamp": item.get("timestamp", time.time()),
                        "message": f"Vehículo no autorizado detectado: {scanned_plate}",
                        "metadata": {"plate": scanned_plate, "authorized": False}
                    }
                    recent_alerts.insert(0, denied_event)
                    if len(recent_alerts) > 100:
                        recent_alerts.pop()
                    if mqtt_gw:
                        mqtt_gw.client.publish(f"vms/cameras/{cam_id}/alerts/alpr_denied", json.dumps(denied_event), qos=1)
                    for sub_queue in list(sse_subscribers):
                        try:
                            loop.call_soon_threadsafe(sub_queue.put_nowait, denied_event)
                        except Exception:
                            pass

            elif isinstance(item, dict) and item.get("type") in ["system_notification", "alert"]:
                # Manejo de notificaciones del sistema directas (ej. inyectadas por orquestador)
                cam_id = item.get("camera", "system")
                notif_msg = item.get("message", "")
                sev = item.get("severity", "info")
                system_notif = {
                    "alert_id": f"sys_{int(time.time()*1000)}",
                    "camera_id": cam_id,
                    "rule_id": "rule_system_notif",
                    "rule_type": "system",
                    "severity": sev,
                    "timestamp": time.time(),
                    "message": notif_msg,
                    "metadata": item
                }
                recent_alerts.insert(0, system_notif)
                if len(recent_alerts) > 100:
                    recent_alerts.pop()
                for sub_queue in list(sse_subscribers):
                    try:
                        loop.call_soon_threadsafe(sub_queue.put_nowait, system_notif)
                    except Exception:
                        pass

            elif isinstance(item, dict) and item.get("type") == "access_control":
                # Control de Acceso por Matrícula (ALPR Whitelist)
                plate = item.get("plate", "DESCONOCIDA")
                cam_id = item.get("camera", "cam_parking")
                action = item.get("action", "")

                logger.info(
                    f">> [CONTROL DE ACCESO] Evento recibido: Cámara='{cam_id}', "
                    f"Acción='{action}', Matrícula='{plate}' <<"
                )

                # 1. Apertura física de barrera vía Modbus TCP (PLC Siemens / WAGO)
                if action == "open_barrier":
                    try:
                        from gateways.barrier_gateway import ModbusBarrierGateway
                        barrier_gw = ModbusBarrierGateway()
                        # Disparo no bloqueante: FC05 Write Single Coil (True) -> 2s sleep -> False
                        barrier_coil = int(os.getenv("PLC_BARRIER_COIL", "0"))
                        barrier_gw.trigger_barrier(coil_address=barrier_coil)
                        logger.info(f">> [PLC BARRERA] Comando de apertura enviado al autómata para [{plate}] en Coil {barrier_coil} <<")
                    except Exception as plc_err:
                        logger.error(f"[PLC BARRERA] Excepción controlada comunicando con autómata: {plc_err}")

                # 2. Publicación en broker MQTT local
                if mqtt_gw:
                    mqtt_topic = f"vms/cameras/{cam_id}/access_control"
                    mqtt_gw.client.publish(mqtt_topic, json.dumps(item), qos=1)

                # 3. Registrar en historial y emitir alerta visual para la UI
                access_alert = {
                    "alert_id": f"alpr_{plate}_{int(time.time())}",
                    "camera_id": cam_id,
                    "rule_id": "rule_alpr_barrier",
                    "rule_type": "access_control",
                    "severity": "info",
                    "timestamp": item.get("timestamp", time.time()),
                    "message": f"Acceso Concedido: Matrícula [{plate}] (Apertura de Barrera PLC)",
                    "metadata": item
                }
                recent_alerts.insert(0, access_alert)
                if len(recent_alerts) > 100:
                    recent_alerts.pop()

                # 4. Difusión inmediata a clientes SSE (Tauri Frontend)
                for sub_queue in list(sse_subscribers):
                    try:
                        loop.call_soon_threadsafe(sub_queue.put_nowait, access_alert)
                    except Exception:
                        pass



            elif isinstance(item, TelemetryData):
                # 1. Escritura asíncrona en InfluxDB Line Protocol
                if influx_gw:
                    influx_gw.write_telemetry(item)

                # 2. Actualización de registros Modbus TCP
                if modbus_gw:
                    modbus_gw.update_occupancy(item.in_count, item.out_count)

                # 3. Actualización de caché de telemetría en memoria
                telemetry_cache[item.camera_id] = {
                    "camera_id": item.camera_id,
                    "timestamp": item.timestamp,
                    "in_count": item.in_count,
                    "out_count": item.out_count,
                    "active_occupancy": item.active_occupancy,
                    "active_tracks": item.active_tracks,
                    "fps": item.fps,
                    "motion_detected": item.motion_detected,
                    "is_standby": item.is_standby
                }

        except Exception as e:
            logger.error(f"Error procesando evento en despachador IPC: {str(e)}")

# ==============================================================================
# CICLO DE VIDA (LIFESPAN) DE FASTAPI
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global influx_gw, mqtt_gw, modbus_gw, midnight_cron
    logger.info("=== INICIANDO CASVMS ENGINE ===")
    
    # 1. Inicialización de Gateways I/O
    if InfluxTelemetryGateway:
        try:
            influx_gw = InfluxTelemetryGateway()
        except Exception as e:
            logger.error(f"Error initializing InfluxDB gateway: {e}")
    if MQTTIndustrialGateway:
        try:
            mqtt_gw = MQTTIndustrialGateway()
        except Exception as e:
            logger.error(f"Error initializing MQTT gateway: {e}")
    if ModbusIndustrialGateway:
        try:
            modbus_gw = ModbusIndustrialGateway()
            modbus_gw.start()
        except Exception as e:
            logger.error(f"Error initializing Modbus gateway: {e}")

    # 2. Iniciar procesos hijos de cámaras desde configuración persistente
    device = os.getenv("OPENVINO_DEVICE", "CPU")
    configured_cameras = load_cameras_config()
    for cam_cfg in configured_cameras:
        start_camera_worker(cam_cfg, device)

    # 3. Iniciar Cron interno de medianoche
    def on_midnight_reset():
        if modbus_gw:
            modbus_gw.update_occupancy(0, 0)
        logger.info("[SISTEMA] Reset global de aforo ejecutado a medianoche.")

    if MidnightResetCron:
        try:
            midnight_cron = MidnightResetCron(
                reset_events=camera_reset_events,
                on_reset_callback=on_midnight_reset
            )
            midnight_cron.start()
        except Exception as e:
            logger.error(f"Error initializing MidnightResetCron: {e}")

    # 4. Iniciar hilo despachador de eventos IPC
    loop = asyncio.get_running_loop()
    import threading
    t = threading.Thread(target=event_dispatcher_worker, args=(event_queue, loop), daemon=True)
    t.start()

    # 5. Iniciar Scheduler ONVIF para conmutación automática Día / Noche ALPR
    try:
        from gateways.onvif_imaging import ONVIFScheduleDaemon
        onvif_scheduler = ONVIFScheduleDaemon()
        onvif_scheduler.start()
    except Exception as onvif_err:
        logger.warning(f"No se pudo iniciar ONVIF Schedule Daemon: {onvif_err}")

    yield

    # ================= APAGADO LIMPIO =================
    logger.info("=== APAGANDO CASVMS ENGINE ===")
    if onvif_scheduler:
        try:
            onvif_scheduler.stop()
        except Exception:
            pass
    if midnight_cron:
        midnight_cron.stop()
    if modbus_gw:
        modbus_gw.stop()
    if mqtt_gw:
        mqtt_gw.close()
    if influx_gw:
        influx_gw.close()

    # Detener procesos hijos

    for cam_id, evt in camera_stop_events.items():
        evt.set()
    for cam_id, proc in camera_processes.items():
        proc.join(timeout=2.0)
    logger.info("Procesos hijos detenidos exitosamente.")

# ==============================================================================
# APLICACIÓN FASTAPI
# ==============================================================================
app = FastAPI(
    title="CASVMS Industrial Edge AI Engine",
    description="Video Management System con analítica OpenVINO iGPU y gateways industriales",
    version="1.0.0",
    lifespan=lifespan
)

# CORS permisivo para interoperar con Tauri Desktop
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# ENDPOINTS REST & STREAMING
# ==============================================================================

@app.get("/health")
def healthcheck():
    """Healthcheck para Docker y balanceadores."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "active_cameras": len(camera_processes),
        "openvino_device": os.getenv("OPENVINO_DEVICE", "GPU")
    }

@app.get("/stream/{camera_id}")
async def mjpeg_stream(camera_id: str):
    """
    Endpoint de streaming MJPEG de latencia sub-100ms.
    Consume los frames codificados a JPEG directamente del diccionario IPC compartido.
    """
    if camera_id not in camera_processes:
        raise HTTPException(status_code=404, detail=f"Cámara '{camera_id}' no encontrada.")

    async def frame_generator():
        while True:
            # Lectura del frame JPEG desde la memoria compartida
            jpeg_bytes = shared_frames.get(camera_id)
            if jpeg_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n\r\n"
                    + jpeg_bytes + b"\r\n"
                )
            # ~25 FPS (cadencia de 40ms)
            await asyncio.sleep(0.04)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/alerts/sse")
async def sse_alerts_endpoint(request: Request):
    """
    Server-Sent Events (SSE) para emisión de alertas en tiempo real hacia la UI de Tauri.
    """
    client_queue = asyncio.Queue()
    sse_subscribers.append(client_queue)

    async def event_generator():
        try:
            # Enviar saludo inicial y alertas recientes
            for past_alert in reversed(recent_alerts[:10]):
                yield {
                    "event": "alert",
                    "data": json.dumps(past_alert)
                }

            while True:
                # Si el cliente desconecta, romper bucle
                if await request.is_disconnected():
                    break
                alert_data = await client_queue.get()
                yield {
                    "event": "alert",
                    "data": json.dumps(alert_data)
                }
        finally:
            if client_queue in sse_subscribers:
                sse_subscribers.remove(client_queue)

    return EventSourceResponse(event_generator())

# ==============================================================================
# ENDPOINTS REST: GESTIÓN E IMPORTACIÓN DE CÁMARAS
# ==============================================================================

class CameraSaveRequest(BaseModel):
    id: str
    name: str
    rtsp_url: str
    enabled: Optional[bool] = True
    onvif_ip: Optional[str] = ""
    onvif_port: Optional[int] = 80
    rules: Optional[Dict[str, Any]] = None

class CameraImportRequest(BaseModel):
    cameras: Optional[List[Dict[str, Any]]] = None
    csv_text: Optional[str] = None
    replace_all: Optional[bool] = False

class StreamTestRequest(BaseModel):
    rtsp_url: str

@app.get("/api/cameras")
def get_cameras():
    """Retorna la lista de cámaras configuradas y su estado de ejecución."""
    cameras_status = []
    cams = load_cameras_config()
    for cam in cams:
        cam_id = cam["id"]
        proc = camera_processes.get(cam_id)
        telemetry = telemetry_cache.get(cam_id, {})
        cameras_status.append({
            "id": cam_id,
            "name": cam["name"],
            "rtsp_url": cam["rtsp_url"],
            "enabled": cam.get("enabled", True),
            "onvif_ip": cam.get("onvif_ip", ""),
            "onvif_port": cam.get("onvif_port", 80),
            "is_alive": proc.is_alive() if proc else False,
            "pid": proc.pid if proc else None,
            "telemetry": telemetry,
            "rules": cam.get("rules", {"tripwires": [], "zones": []})
        })
    return cameras_status

@app.post("/api/cameras")
def save_camera(req: CameraSaveRequest):
    """Crea o actualiza una cámara individual de forma persistente."""
    cams = load_cameras_config()
    device = os.getenv("OPENVINO_DEVICE", "CPU")
    existing_idx = next((i for i, c in enumerate(cams) if c["id"] == req.id), -1)
    
    default_rules = {"tripwires": [], "zones": []}
    cam_data = {
        "id": req.id,
        "name": req.name,
        "rtsp_url": req.rtsp_url,
        "enabled": req.enabled if req.enabled is not None else True,
        "onvif_ip": req.onvif_ip or "",
        "onvif_port": req.onvif_port or 80,
        "rules": req.rules if req.rules is not None else (cams[existing_idx].get("rules", default_rules) if existing_idx >= 0 else default_rules)
    }
    
    if existing_idx >= 0:
        cams[existing_idx] = cam_data
    else:
        cams.append(cam_data)
        
    save_cameras_config(cams)
    if cam_data["enabled"]:
        start_camera_worker(cam_data, device)
    else:
        stop_camera_worker(req.id)
        
    return {"status": "success", "camera": cam_data, "message": f"Cámara '{req.name}' guardada correctamente."}

@app.delete("/api/cameras/{cam_id}")
def delete_camera(cam_id: str):
    """Elimina una cámara y detiene su proceso worker."""
    cams = load_cameras_config()
    filtered = [c for c in cams if c["id"] != cam_id]
    if len(filtered) == len(cams):
        raise HTTPException(status_code=404, detail="Cámara no encontrada.")
    save_cameras_config(filtered)
    stop_camera_worker(cam_id)
    return {"status": "success", "message": f"Cámara '{cam_id}' eliminada del sistema."}

@app.post("/api/cameras/import")
def import_cameras_endpoint(req: CameraImportRequest):
    """Importación masiva de cámaras desde JSON o texto CSV."""
    device = os.getenv("OPENVINO_DEVICE", "CPU")
    imported_list = []
    
    if req.cameras:
        imported_list = req.cameras
    elif req.csv_text:
        import csv
        import io
        try:
            reader = csv.DictReader(io.StringIO(req.csv_text.strip()))
            for row in reader:
                cid = row.get("id") or row.get("camera_id") or f"cam_{int(time.time()*1000)}"
                imported_list.append({
                    "id": cid.strip(),
                    "name": (row.get("name") or cid).strip(),
                    "rtsp_url": (row.get("rtsp_url") or "demo").strip(),
                    "enabled": str(row.get("enabled", "true")).lower() in ["true", "1", "yes"],
                    "onvif_ip": (row.get("onvif_ip") or "").strip(),
                    "onvif_port": int(row.get("onvif_port") or 80),
                    "rules": {"tripwires": [], "zones": []}
                })
        except Exception as csv_err:
            raise HTTPException(status_code=400, detail=f"Error parseando CSV: {str(csv_err)}")
            
    if not imported_list:
        raise HTTPException(status_code=400, detail="No se encontraron registros de cámaras válidos.")
        
    current = [] if req.replace_all else load_cameras_config()
    current_ids = {c["id"]: i for i, c in enumerate(current)}
    
    for cam in imported_list:
        cid = cam.get("id")
        if not cid:
            continue
        clean_cam = {
            "id": str(cid).strip(),
            "name": str(cam.get("name", cid)).strip(),
            "rtsp_url": str(cam.get("rtsp_url", "demo")).strip(),
            "enabled": bool(cam.get("enabled", True)),
            "onvif_ip": str(cam.get("onvif_ip", "")).strip(),
            "onvif_port": int(cam.get("onvif_port", 80)),
            "rules": cam.get("rules", {"tripwires": [], "zones": []})
        }
        if cid in current_ids:
            current[current_ids[cid]] = clean_cam
        else:
            current.append(clean_cam)
            
    save_cameras_config(current)
    
    # Iniciar workers activos
    for cam in current:
        if cam.get("enabled", True):
            start_camera_worker(cam, device)
        else:
            stop_camera_worker(cam["id"])
            
    return {
        "status": "success",
        "imported_count": len(imported_list),
        "total_cameras": len(current),
        "message": f"Se han importado {len(imported_list)} cámaras correctamente."
    }

@app.post("/api/cameras/discover-onvif")
def discover_onvif_endpoint():
    """Sondeo WS-Discovery en la red local para auto-detectar cámaras ONVIF."""
    devices = discover_onvif_devices(timeout=2.5)
    return {"status": "success", "devices": devices, "total": len(devices)}

@app.post("/api/cameras/test-stream")
def test_stream_endpoint(req: StreamTestRequest):
    """Prueba la disponibilidad y resolución de un stream RTSP."""
    res = test_rtsp_connection(req.rtsp_url)
    return res


# ==============================================================================
# ENDPOINTS REST: CONFIGURACIÓN Y SALIDAS MODBUS TCP
# ==============================================================================

class ModbusTestOutputRequest(BaseModel):
    coil_address: Optional[int] = 0
    pulse_duration: Optional[float] = 2.0
    action: Optional[str] = "pulse"  # "pulse" o "write_register"
    register_address: Optional[int] = None
    register_value: Optional[int] = None
    plc_host: Optional[str] = None
    plc_port: Optional[int] = None
    slave_id: Optional[int] = 1

@app.get("/api/modbus/config")
def get_modbus_config_endpoint():
    """Retorna la configuración completa de Modbus Server, PLC y mapeo de salidas."""
    cfg = load_modbus_config()
    return {"status": "success", "config": cfg}

@app.post("/api/modbus/config")
def update_modbus_config_endpoint(cfg: Dict[str, Any]):
    """Actualiza y persiste la configuración de Modbus."""
    save_modbus_config(cfg)
    if modbus_gw and "server" in cfg:
        cap = cfg["server"].get("capacity_limit", 50)
        modbus_gw.capacity_limit = cap
        modbus_gw.write_holding_register(5, cap)
    return {"status": "success", "message": "Configuración Modbus guardada correctamente.", "config": cfg}

@app.get("/api/modbus/status")
def get_modbus_status_endpoint():
    """Retorna el estado de los registros Holding y el servidor Modbus."""
    cfg = load_modbus_config()
    reg_values = modbus_gw.get_all_registers(count=12) if modbus_gw else {}
    server_running = modbus_gw.is_running() if modbus_gw else False
    return {
        "status": "success",
        "server_running": server_running,
        "host": cfg.get("server", {}).get("host", "0.0.0.0"),
        "port": cfg.get("server", {}).get("port", 5020),
        "slave_id": cfg.get("server", {}).get("slave_id", 1),
        "plc_host": cfg.get("plc_client", {}).get("host", "192.168.1.50"),
        "plc_port": cfg.get("plc_client", {}).get("port", 502),
        "registers": reg_values,
        "output_mappings": cfg.get("output_mappings", {})
    }

@app.post("/api/modbus/test-output")
def test_modbus_output_endpoint(req: ModbusTestOutputRequest):
    """Dispara un pulso de prueba a una bobina/relé de PLC o escribe en un registro Modbus."""
    if req.action == "write_register":
        if req.register_address is None or req.register_value is None:
            raise HTTPException(status_code=400, detail="Debe especificar register_address y register_value.")
        if modbus_gw:
            ok = modbus_gw.write_holding_register(req.register_address, req.register_value)
            return {"status": "success" if ok else "error", "message": f"Registro {req.register_address} escrito con valor {req.register_value}."}
        else:
            raise HTTPException(status_code=500, detail="Servidor Modbus no está activo.")

    # Disparo de pulso de relé a PLC externo
    try:
        from gateways.barrier_gateway import ModbusBarrierGateway
        gw = ModbusBarrierGateway(
            host=req.plc_host,
            port=req.plc_port,
            slave_id=req.slave_id,
            pulse_duration_seconds=req.pulse_duration or 2.0
        )
        res = gw.test_pulse_sync(
            coil_address=req.coil_address or 0,
            pulse_duration=req.pulse_duration or 2.0,
            slave_id=req.slave_id
        )
        return res
    except Exception as e:
        return {"success": False, "error": f"Excepción ejecutando prueba Modbus: {str(e)}"}


@app.get("/api/telemetry")
def get_telemetry():
    """Retorna métricas consolidadas de telemetría y aforo."""
    total_in = sum(t.get("in_count", 0) for t in telemetry_cache.values())
    total_out = sum(t.get("out_count", 0) for t in telemetry_cache.values())
    total_occupancy = max(0, total_in - total_out)
    return {
        "timestamp": time.time(),
        "total_in": total_in,
        "total_out": total_out,
        "total_occupancy": total_occupancy,
        "cameras": telemetry_cache,
        "recent_alerts_count": len(recent_alerts)
    }

@app.get("/api/recordings")
def list_recordings():
    """Lista todos los clips MP4 exportados por el Smart DVR con sus metadatos."""
    clips = []
    mp4_files = glob.glob(os.path.join(RECORDINGS_DIR, "*.mp4"))
    
    for filepath in sorted(mp4_files, reverse=True):
        filename = os.path.basename(filepath)
        meta_filepath = f"{filepath}.json"
        meta = {}
        if os.path.exists(meta_filepath):
            try:
                with open(meta_filepath, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
                
        file_size = os.path.getsize(filepath)
        clips.append({
            "filename": filename,
            "filepath": filepath,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "created_at": os.path.getmtime(filepath),
            "metadata": meta
        })
    return clips

@app.get("/api/recordings/{filename}")
def stream_recording(filename: str):
    """Descarga o reproduce un clip MP4 grabado por el Smart DVR."""
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(RECORDINGS_DIR, safe_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Archivo de grabación no encontrado.")
    return FileResponse(filepath, media_type="video/mp4", filename=safe_filename)

@app.post("/api/system/reset-counts")
def manual_reset_counts():
    """Dispara un reseteo manual de contadores de aforo en todas las cámaras y en Modbus."""
    for evt in camera_reset_events:
        evt.set()
    if modbus_gw:
        modbus_gw.update_occupancy(0, 0)
    return {"status": "success", "message": "Contadores reseteados correctamente."}

# ==============================================================================
# ENDPOINTS REST: CONTROL DE ACCESO ALPR (WHITELIST SQLITE)
# ==============================================================================

class ALPRWhitelistRequest(BaseModel):
    plate: Optional[str] = None
    plate_number: Optional[str] = None
    owner: Optional[str] = ""
    owner_name: Optional[str] = ""
    vehicle_model: Optional[str] = ""

    def get_plate(self) -> str:
        return (self.plate or self.plate_number or "").strip()

    def get_owner(self) -> str:
        return (self.owner or self.owner_name or "").strip()

@app.get("/api/alpr/whitelist")
@app.get("/api/plates")
def list_authorized_plates():
    """Retorna todas las matrículas autorizadas registradas en la base de datos SQLite."""
    from core.plate_whitelist import PlateWhitelistManager
    manager = PlateWhitelistManager()
    plates = manager.get_all_plates()
    records = [
        {
            "id": p.get("id"),
            "plate": p.get("plate_number") or p.get("plate", ""),
            "plate_number": p.get("plate_number") or p.get("plate", ""),
            "normalized_plate": p.get("normalized_plate", ""),
            "owner": p.get("owner_name") or p.get("owner", ""),
            "owner_name": p.get("owner_name") or p.get("owner", ""),
            "vehicle_model": p.get("vehicle_model", ""),
            "added_at": p.get("created_at") or p.get("added_at", ""),
            "created_at": p.get("created_at") or p.get("added_at", ""),
            "is_active": p.get("is_active", 1)
        }
        for p in plates
    ]
    return {
        "status": "success",
        "records": records,
        "total": len(records)
    }

@app.post("/api/alpr/whitelist")
@app.post("/api/plates")
def add_authorized_plate(plate_req: ALPRWhitelistRequest):
    """Añade o actualiza una matrícula autorizada en la Whitelist SQLite."""
    plate_str = plate_req.get_plate()
    if not plate_str:
        raise HTTPException(status_code=400, detail="El campo 'plate' es obligatorio.")
    from core.plate_whitelist import PlateWhitelistManager
    manager = PlateWhitelistManager()
    success = manager.add_plate(
        plate_number=plate_str,
        owner_name=plate_req.get_owner(),
        vehicle_model=plate_req.vehicle_model or ""
    )
    if not success:
        raise HTTPException(status_code=400, detail="Error registrando la matrícula.")
    return {
        "status": "success",
        "message": f"Matrícula '{plate_str.upper()}' autorizada para control de acceso.",
        "plate": plate_str.upper(),
        "owner": plate_req.get_owner()
    }

@app.delete("/api/alpr/whitelist/{plate}")
@app.delete("/api/plates/{plate}")
def delete_authorized_plate(plate: str):
    """Elimina una matrícula de la lista de autorizados de SQLite."""
    from core.plate_whitelist import PlateWhitelistManager
    manager = PlateWhitelistManager()
    deleted = manager.delete_plate(plate)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Matrícula '{plate}' no encontrada.")
    return {
        "status": "success",
        "message": f"Matrícula '{plate}' eliminada del sistema de acceso."
    }


@app.get("/api/plates/verify/{plate}")
def verify_plate_access(plate: str):
    """Verifica si una matrícula específica tiene acceso concedido para apertura de barrera."""
    from core.plate_whitelist import PlateWhitelistManager
    manager = PlateWhitelistManager()
    authorized = manager.is_plate_authorized(plate)
    return {
        "plate": plate,
        "normalized": manager.normalize_plate(plate),
        "authorized": authorized,
        "action": "open_barrier" if authorized else "deny_access"
    }

# ==============================================================================
# ENDPOINTS REST: CONTROL ÓPTICO ONVIF (PERFILES DÍA / NOCHE ALPR)
# ==============================================================================

@app.post("/api/cameras/{camera_id}/imaging/{mode}")
def set_camera_imaging_profile(camera_id: str, mode: str):
    """
    Aplica el perfil óptico ONVIF a la cámara:
    - 'night': IrCutFilter='OFF' (Infrarrojo B/N), Shutter 1/1000s, WDR OFF (Anti-blur ALPR).
    - 'day': IrCutFilter='ON' (Color diurno), Shutter Auto, WDR ON.
    """
    if mode.lower() not in ["night", "day"]:
        raise HTTPException(status_code=400, detail="Modo no soportado. Especifique 'night' o 'day'.")

    from gateways.onvif_imaging import ONVIFImagingController

    cam_ip = os.getenv("ONVIF_CAMERA_IP", "192.168.1.64")
    cam_port = int(os.getenv("ONVIF_CAMERA_PORT", "80"))
    cam_user = os.getenv("ONVIF_CAMERA_USER", "admin")
    cam_pass = os.getenv("ONVIF_CAMERA_PASS", "admin123")

    controller = ONVIFImagingController(
        ip=cam_ip,
        port=cam_port,
        user=cam_user,
        password=cam_pass
    )
    controller.apply_profile_async(mode)

    return {
        "status": "success",
        "camera_id": camera_id,
        "mode": mode.lower(),
        "message": f"Comando de perfil óptico ONVIF ({mode.upper()}) despachado a la cámara."
    }

if __name__ == "__main__":


    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
