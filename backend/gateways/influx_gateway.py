# ==============================================================================
# CASVMS - InfluxDB 2.7 Telemetry Gateway
# ==============================================================================
import os
import time
import logging
from typing import Optional
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from core.types import TelemetryData

logger = logging.getLogger("CASVMS.Gateway.InfluxDB")

class InfluxTelemetryGateway:
    """
    Gateway asíncrono para almacenamiento de telemetría de series temporales en InfluxDB 2.7.
    Registra métricas de aforo (IN/OUT), ocupación activa, FPS y estado de Standby mediante Line Protocol.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None
    ):
        self.url = url or os.getenv("INFLUXDB_URL", "http://influxdb:8086")
        self.token = token or os.getenv("INFLUXDB_TOKEN", "casvms_super_secret_token_123456789_abcdef")
        self.org = org or os.getenv("INFLUXDB_ORG", "casvms")
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", "telemetry")
        
        self.client: Optional[InfluxDBClient] = None
        self.write_api = None
        self._is_connected = False
        
        self._connect()

    def _connect(self) -> None:
        """Establece la conexión con la instancia de InfluxDB."""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=5000,
                enable_gzip=True
            )
            # Modo batch síncrono no bloqueante
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self._is_connected = True
            logger.info(f"Conexión exitosa a InfluxDB en {self.url} (Org: {self.org}, Bucket: {self.bucket}).")
        except Exception as e:
            self._is_connected = False
            logger.warning(f"No se pudo conectar inmediatamente a InfluxDB ({str(e)}). Se reintentará en el primer envío.")

    def write_telemetry(self, data: TelemetryData) -> bool:
        """
        Escribe un punto de medición en InfluxDB usando Line Protocol.
        """
        try:
            if not self._is_connected or self.write_api is None:
                self._connect()
                if not self._is_connected or self.write_api is None:
                    return False

            point = (
                Point("camera_telemetry")
                .tag("camera_id", data.camera_id)
                .field("in_count", int(data.in_count))
                .field("out_count", int(data.out_count))
                .field("active_occupancy", int(data.active_occupancy))
                .field("active_tracks", int(data.active_tracks))
                .field("fps", float(data.fps))
                .field("motion_detected", bool(data.motion_detected))
                .field("is_standby", bool(data.is_standby))
                .time(int(data.timestamp * 1e9))  # Nanosegundos para InfluxDB
            )

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            return True

        except Exception as e:
            logger.error(f"Error escribiendo telemetría en InfluxDB: {str(e)}")
            self._is_connected = False
            return False

    def close(self) -> None:
        """Cierra el cliente de InfluxDB y flushea buffers pendientes."""
        if self.write_api:
            try:
                self.write_api.close()
            except Exception:
                pass
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        logger.info("Gateway InfluxDB cerrado.")
