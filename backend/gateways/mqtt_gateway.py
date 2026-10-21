# ==============================================================================
# CASVMS - MQTT Industrial Gateway (Paho-MQTT)
# ==============================================================================
import os
import json
import logging
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt

from core.types import AlertEvent, Severity

logger = logging.getLogger("CASVMS.Gateway.MQTT")

class MQTTIndustrialGateway:
    """
    Gateway MQTT para emisión de alarmas y estados hacia SCADAs, Node-RED y Home Assistant.
    Publica alertas en tópicos jerárquicos normalizados:
    - vms/cameras/{camera_id}/alarms/{rule_type}
    - vms/cameras/{camera_id}/occupancy
    """

    def __init__(
        self,
        broker: Optional[str] = None,
        port: Optional[int] = None,
        client_id: str = "casvms_engine"
    ):
        self.broker = broker or os.getenv("MQTT_BROKER", "mosquitto")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.client_id = client_id
        
        # Paho MQTT Client con reconexión automática
        self.client = mqtt.Client(
            client_id=self.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311
        )
        
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        self._is_connected = False
        self._start()

    def _start(self) -> None:
        """Inicia el bucle de red de MQTT en un hilo en background."""
        try:
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            logger.info(f"Iniciando cliente MQTT conectando a {self.broker}:{self.port}...")
        except Exception as e:
            logger.warning(f"Error inicial conectando a broker MQTT ({self.broker}:{self.port}): {str(e)}")

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._is_connected = True
            logger.info(f"Conexión establecida exitosamente con el broker MQTT ({self.broker}:{self.port}).")
            # Publicar estado de vida (Heartbeat / LWT)
            self.client.publish("vms/system/status", json.dumps({"status": "ONLINE"}), retain=True)
        else:
            self._is_connected = False
            logger.error(f"Fallo de conexión MQTT, código de retorno: {rc}")

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._is_connected = False
        if rc != 0:
            logger.warning("Desconexión inesperada de MQTT. Intentando reconexión automática...")

    def publish_alert(self, alert: AlertEvent) -> bool:
        """
        Publica una alarma crítica o de seguridad en el tópico correspondiente.
        Ejemplo: vms/cameras/cam1/alarms/intrusion
        """
        try:
            # Tópico jerárquico según especificación arquitectónica
            topic = f"vms/cameras/{alert.camera_id}/alarms/{alert.rule_type.value}"
            
            payload = {
                "alert_id": alert.alert_id,
                "camera_id": alert.camera_id,
                "rule_id": alert.rule_id,
                "rule_type": alert.rule_type.value,
                "severity": alert.severity.value,
                "timestamp": alert.timestamp,
                "message": alert.message,
                "metadata": alert.metadata
            }

            # Enviar con QoS 1 para garantizar entrega de alarmas críticas
            qos = 1 if alert.severity in [Severity.HIGH, Severity.CRITICAL] else 0
            info = self.client.publish(topic, json.dumps(payload), qos=qos)
            return info.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error(f"Error publicando alerta en MQTT: {str(e)}")
            return False

    def publish_occupancy(self, camera_id: str, occupancy: int, in_count: int, out_count: int) -> None:
        """Publica el aforo instantáneo para visualizadores industriales."""
        topic = f"vms/cameras/{camera_id}/occupancy"
        payload = {
            "camera_id": camera_id,
            "occupancy": occupancy,
            "in_count": in_count,
            "out_count": out_count
        }
        self.client.publish(topic, json.dumps(payload), qos=0)

    def close(self) -> None:
        """Detiene el cliente MQTT."""
        try:
            self.client.publish("vms/system/status", json.dumps({"status": "OFFLINE"}), retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Gateway MQTT desconectado.")
        except Exception:
            pass
