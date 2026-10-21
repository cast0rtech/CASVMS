# ==============================================================================
# CASVMS - Modbus TCP Parking Barrier Gateway (PLC Relay Pulse Controller)
# ==============================================================================
import os
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger("CASVMS.Gateway.Barrier")

class ModbusBarrierGateway:
    """
    Gateway Modbus TCP para control físico de barreras de aparcamiento vía PLC.
    
    Compatible con autómatas industriales:
    - Siemens LOGO! (0BA8 / 8.3 / 8.4) vía mapeo de bobinas Q1/M1
    - Siemens S7-1200 / S7-1500 (MB_SERVER)
    - WAGO 750 Series / Schneider Electric Modicon
    
    Implementa un ciclo de pulso con auto-reset (contacto seco / dry contact):
    1. Envía señal ON (True) al relé / bobina física (Modbus FC 05: Write Single Coil).
    2. Espera 2 segundos en un hilo desacoplado no bloqueante.
    3. Envía señal OFF (False) a la misma bobina para liberar el relé del autómata.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 502,
        plc_host: Optional[str] = None,
        plc_port: Optional[int] = None,
        slave_unit: int = 1,
        slave_id: Optional[int] = None,
        pulse_duration_seconds: float = 2.0,
        connection_timeout: float = 3.0
    ):
        target_host = host or plc_host or os.getenv("PLC_MODBUS_HOST", "192.168.1.50")
        target_port = port if host is not None else (plc_port or int(os.getenv("PLC_MODBUS_PORT", "502")))
        self.plc_host = target_host
        self.plc_port = target_port
        self.host = target_host
        self.port = target_port
        self.slave_unit = slave_id or slave_unit or int(os.getenv("PLC_MODBUS_SLAVE", "1"))
        self.pulse_duration = pulse_duration_seconds
        self.timeout = connection_timeout
        self._lock = threading.Lock()
        
        try:
            from pymodbus.client import ModbusTcpClient
            self.client = ModbusTcpClient(self.plc_host, port=self.plc_port, timeout=self.timeout)
        except ImportError:
            self.client = None

        logger.info(
            f"ModbusBarrierGateway configurado para PLC en {self.plc_host}:{self.plc_port} "
            f"(Unit ID: {self.slave_unit}, Pulso: {self.pulse_duration}s)."
        )

    def trigger_barrier(self, coil_address: int = 0, slave_id: int = 1) -> None:
        """
        Delega el pulso a un hilo daemon para no bloquear 
        el orquestador principal durante el time.sleep().
        """
        threading.Thread(
            target=self._pulse_coil, 
            args=(coil_address, slave_id), 
            daemon=True
        ).start()

    def open_barrier(self, coil_address: int = 0, plate: str = "", slave_id: Optional[int] = None) -> None:
        """
        Dispara la apertura de la barrera mediante un pulso de relé asíncrono.
        
        Args:
            coil_address: Dirección de la bobina Modbus (Coil) vinculada al relé de apertura.
            plate: Matrícula autorizada que originó la apertura (para logging y auditoría).
            slave_id: ID del esclavo Modbus (opcional, usa self.slave_unit por defecto).
        """
        s_id = slave_id if slave_id is not None else self.slave_unit
        threading.Thread(
            target=self._pulse_coil,
            args=(coil_address, s_id, plate),
            daemon=True,
            name=f"Barrier-Pulse-Coil-{coil_address}"
        ).start()

    def _pulse_coil(self, coil_address: int, slave_id: int = 1, plate: str = "") -> None:
        """
        Secuencia de pulso: Enviar ON (True), esperar 2s, enviar OFF (False).
        """
        try:
            if self.client is None:
                from pymodbus.client import ModbusTcpClient
                self.client = ModbusTcpClient(self.plc_host, port=self.plc_port, timeout=self.timeout)

            if not self.client.connected:
                self.client.connect()
            
            # 1. Enviar pulso ALTO (Cerrar relé / Abrir barrera)
            self.client.write_coil(coil_address, True, slave=slave_id)
            tag = f" para vehículo [{plate}]" if plate else ""
            print(f"[MODBUS] Comando apertura enviado (Coil {coil_address}=1){tag}")
            logger.info(f"[BARRERA PLC] Comando apertura enviado (Coil {coil_address}=1){tag}")
            
            # 2. Mantener el pulso 2 segundos (simulación de contacto seco)
            time.sleep(self.pulse_duration)
            
            # 3. Enviar pulso BAJO (Rearmar circuito)
            self.client.write_coil(coil_address, False, slave=slave_id)
            print(f"[MODBUS] Pulso rearmado (Coil {coil_address}=0)")
            logger.info(f"[BARRERA PLC] Pulso rearmado (Coil {coil_address}=0)")
            
        except Exception as e:
            print(f"[MODBUS] Error de comunicación con PLC: {e}")
            logger.error(f"[BARRERA PLC] Error de comunicación con PLC en {self.plc_host}:{self.plc_port}: {e}")

    def _pulse_worker(self, coil_address: int, plate: str) -> None:
        """Alias de compatibilidad con versiones previas."""
        self._pulse_coil(coil_address=coil_address, slave_id=self.slave_unit, plate=plate)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Actuador de Barrera Modbus TCP para Control de Accesos")
    parser.add_argument("--host", default=os.getenv("PLC_MODBUS_HOST", "192.168.1.50"), help="IP del PLC industrial")
    parser.add_argument("--port", type=int, default=int(os.getenv("PLC_MODBUS_PORT", "502")), help="Puerto Modbus TCP")
    parser.add_argument("--coil", type=int, default=int(os.getenv("PLC_BARRIER_COIL", "0")), help="Dirección del Coil (Relé)")
    parser.add_argument("--slave", type=int, default=1, help="Slave Unit ID")
    parser.add_argument("--plate", default="TEST-1234", help="Matrícula para registro de auditoría")
    
    args = parser.parse_args()
    gw = ModbusBarrierGateway(host=args.host, port=args.port, slave_id=args.slave)
    print(f"Disparando pulso de apertura en PLC {args.host}:{args.port} (Coil {args.coil})...")
    gw.open_barrier(coil_address=args.coil, plate=args.plate)
    # Esperar a que el pulso asíncrono complete para finalizar el CLI
    time.sleep(2.5)

