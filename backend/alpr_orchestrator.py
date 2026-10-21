# ==============================================================================
# CASVMS - ALPR & Modbus Barrier Orchestrator Component
# ==============================================================================
import os
import sys
import time
import multiprocessing as mp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# Asegurar importación de módulos core y gateways
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.plate_whitelist import ALPRWhitelistDB
from gateways.barrier_gateway import ModbusBarrierGateway

# Instanciar las capas de control
alpr_db = ALPRWhitelistDB(db_path=os.getenv("ALPR_DB_PATH", "data/alpr_whitelist.db"))
barrier_gateway = ModbusBarrierGateway(host=os.getenv("PLC_MODBUS_HOST", "192.168.1.50"))

router = APIRouter()

# ==========================================
# 1. ENDPOINTS PARA EL FRONTEND TAURI
# ==========================================
class PlateRecord(BaseModel):
    plate: str
    owner: str

@router.get("/api/alpr/whitelist")
async def list_whitelist():
    records = alpr_db.get_all_plates()
    return {"status": "success", "records": records}

@router.post("/api/alpr/whitelist")
async def register_plate(record: PlateRecord):
    alpr_db.add_plate(record.plate, record.owner)
    return {"status": "success", "message": f"Matrícula {record.plate} autorizada."}

@router.delete("/api/alpr/whitelist/{plate}")
async def remove_plate(plate: str):
    alpr_db.delete_plate(plate)
    return {"status": "success"}

# ==========================================
# 2. HILO ORQUESTADOR (Consumidor IPC)
# ==========================================
def event_routing_pump(alert_queue: mp.Queue):
    """
    Este hilo extrae los eventos generados por los workers de OpenCV (EasyOCR)
    y ejecuta las acciones físicas y de base de datos.
    """
    try:
        while True:
            if not alert_queue.empty():
                event = alert_queue.get()
                
                # Interceptar evento de lectura de matrícula
                if isinstance(event, dict) and event.get("type") == "alpr_read":
                    scanned_plate = event.get("plate", "")
                    cam_id = event.get("camera", "cam_parking")
                    direction = event.get("direction", "UNKNOWN")
                    
                    # Cruzar lectura con SQLite local
                    access_info = alpr_db.check_access(scanned_plate)
                    
                    if access_info:
                        print(f"[ALPR] Acceso AUTORIZADO: {scanned_plate} ({access_info['owner']}) [Rumbo: {direction}]")
                        
                        # 1. Disparar PLC vía Modbus (Coil 0 es el relé 1)
                        barrier_gateway.trigger_barrier(coil_address=0)
                        
                        # 2. Enviar notificación al frontend (Panel SSE)
                        alert_queue.put({
                            "type": "system_notification",
                            "camera": cam_id,
                            "direction": direction,
                            "message": f"Barrera abierta para {access_info['owner']} [{scanned_plate}] ({direction})",
                            "severity": "info"
                        })
                    else:
                        print(f"[ALPR] Acceso DENEGADO: {scanned_plate} [Rumbo: {direction}]")
                        # Lanzar alerta crítica de intento de acceso
                        alert_queue.put({
                            "type": "alert",
                            "camera": cam_id,
                            "direction": direction,
                            "message": f"Vehículo no autorizado detectado: {scanned_plate} ({direction})",
                            "severity": "high"
                        })
            else:
                time.sleep(0.01)
                
    except Exception as e:
        print(f"[ORCHESTRATOR] Error en el bus de eventos: {e}")
