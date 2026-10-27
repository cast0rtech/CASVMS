# ==============================================================================
# CASVMS - Configuration Persistence Manager (Cameras & Modbus I/O)
# ==============================================================================
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("CASVMS.ConfigManager")

CONFIG_DIR = os.getenv("CONFIG_DIR", "/app/config")
CAMERAS_CONFIG_FILE = os.path.join(CONFIG_DIR, "cameras.json")
MODBUS_CONFIG_FILE = os.path.join(CONFIG_DIR, "modbus_config.json")

# Configuración inicial predeterminada de cámaras
DEFAULT_CAMERAS_SEED = [
    {
        "id": "cam_01",
        "name": "Acceso Principal y Perímetro",
        "rtsp_url": "demo",
        "enabled": True,
        "rules": {
            "tripwires": [
                {
                    "rule_id": "tw_entry_01",
                    "name": "Torniquete Entrada/Salida",
                    "pt1": [400.0, 200.0],
                    "pt2": [880.0, 200.0],
                    "target_classes": ["person"],
                    "enabled": True
                }
            ],
            "zones": [
                {
                    "rule_id": "zn_restricted_01",
                    "name": "Zona Restringida Sala Eléctrica",
                    "polygon": [[200.0, 350.0], [600.0, 350.0], [600.0, 650.0], [200.0, 650.0]],
                    "rule_type": "intrusion",
                    "target_classes": ["person"],
                    "enabled": True
                }
            ]
        }
    },
    {
        "id": "cam_parking",
        "name": "Acceso Parking y Barrera ALPR",
        "rtsp_url": "demo",
        "enabled": True,
        "rules": {
            "tripwires": [
                {
                    "rule_id": "tw_barrier_line",
                    "name": "Línea de Barrera",
                    "pt1": [300.0, 500.0],
                    "pt2": [980.0, 500.0],
                    "target_classes": ["car", "truck", "motorcycle"],
                    "enabled": True
                }
            ],
            "zones": [
                {
                    "rule_id": "zn_barrier_roi",
                    "name": "Zona de Lectura de Matrículas (Barrera)",
                    "polygon": [[250.0, 320.0], [1050.0, 320.0], [1050.0, 700.0], [250.0, 700.0]],
                    "rule_type": "dwell_time",
                    "max_dwell_seconds": 10.0,
                    "target_classes": ["car", "truck", "bus", "motorcycle"],
                    "enabled": True
                }
            ]
        }
    }
]

# Configuración inicial predeterminada de Modbus I/O
DEFAULT_MODBUS_CONFIG = {
    "server": {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 5020,
        "slave_id": 1,
        "capacity_limit": 50
    },
    "plc_client": {
        "enabled": True,
        "host": "192.168.1.50",
        "port": 502,
        "slave_unit": 1,
        "timeout": 3.0
    },
    "output_mappings": {
        "barrier_relay": {
            "name": "Apertura de Barrera ALPR",
            "enabled": True,
            "coil_address": 0,
            "pulse_duration": 2.0,
            "description": "Pulso de relé (contacto seco) para accionador de barrera al validar matrícula"
        },
        "intrusion_alarm": {
            "name": "Alarma de Intrusión Perimetral",
            "enabled": True,
            "coil_address": 1,
            "pulse_duration": 3.0,
            "description": "Pulso a sirena o PLC cuando se detecta persona en zona restringida"
        },
        "overcapacity_alarm": {
            "name": "Alarma de Sobre-aforo",
            "enabled": True,
            "coil_address": 2,
            "pulse_duration": 5.0,
            "description": "Señal a PLC cuando el aforo actual supera el límite configurado"
        },
        "tripwire_trigger": {
            "name": "Disparo por Cruce de Línea",
            "enabled": False,
            "coil_address": 3,
            "pulse_duration": 1.5,
            "description": "Pulso de relé al cruzar torniquete o línea virtual"
        }
    },
    "register_mappings": {
        "occupancy_reg": 0,
        "overcapacity_flag_reg": 1,
        "in_count_reg": 2,
        "out_count_reg": 3,
        "intrusion_flag_reg": 4,
        "capacity_limit_reg": 5,
        "barrier_status_reg": 6,
        "alarm_status_reg": 7
    }
}

def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load_cameras_config() -> List[Dict[str, Any]]:
    """Carga la lista de cámaras desde disco, o genera la configuración base si no existe."""
    ensure_config_dir()
    if os.path.exists(CAMERAS_CONFIG_FILE):
        try:
            with open(CAMERAS_CONFIG_FILE, "r", encoding="utf-8") as f:
                cams = json.load(f)
                if isinstance(cams, list) and len(cams) > 0:
                    return cams
        except Exception as e:
            logger.error(f"Error leyendo {CAMERAS_CONFIG_FILE}: {e}. Usando valores predeterminados.")
    
    # Si no existe o falló, guardar el seed
    save_cameras_config(DEFAULT_CAMERAS_SEED)
    return DEFAULT_CAMERAS_SEED

def save_cameras_config(cameras: List[Dict[str, Any]]) -> bool:
    """Guarda la lista de cámaras de forma persistente en JSON."""
    ensure_config_dir()
    try:
        with open(CAMERAS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cameras, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuración de {len(cameras)} cámaras guardada en {CAMERAS_CONFIG_FILE}.")
        return True
    except Exception as e:
        logger.error(f"Error guardando cámaras en {CAMERAS_CONFIG_FILE}: {e}")
        return False

def load_modbus_config() -> Dict[str, Any]:
    """Carga la configuración de Modbus Server y Salidas PLC desde disco."""
    ensure_config_dir()
    if os.path.exists(MODBUS_CONFIG_FILE):
        try:
            with open(MODBUS_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                # Fusionar con defaults para compatibilidad de claves nuevas
                merged = dict(DEFAULT_MODBUS_CONFIG)
                merged.update(cfg)
                return merged
        except Exception as e:
            logger.error(f"Error leyendo {MODBUS_CONFIG_FILE}: {e}. Usando valores predeterminados.")
            
    save_modbus_config(DEFAULT_MODBUS_CONFIG)
    return DEFAULT_MODBUS_CONFIG

def save_modbus_config(cfg: Dict[str, Any]) -> bool:
    """Guarda la configuración de Modbus en disco."""
    ensure_config_dir()
    try:
        with open(MODBUS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuración Modbus guardada en {MODBUS_CONFIG_FILE}.")
        return True
    except Exception as e:
        logger.error(f"Error guardando configuración Modbus: {e}")
        return False
