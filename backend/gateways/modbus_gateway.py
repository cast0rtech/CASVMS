# ==============================================================================
# CASVMS - Modbus TCP Industrial Gateway (PLC / SCADA Integration)
# ==============================================================================
import os
import asyncio
import logging
import threading
from typing import Optional

from pymodbus.server.async_io import ModbusTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext
)

logger = logging.getLogger("CASVMS.Gateway.Modbus")

class ModbusIndustrialGateway:
    """
    Gateway Modbus TCP para comunicación con Autómatas Programables (PLCs: Siemens, WAGO, Schneider).
    
    Mapeo de Holding Registers (Dirección base 40001 / offset 0):
      - Registro 0: Aforo actual total (Ocupación).
      - Registro 1: Bandera de alarma de sobre-aforo (1 = Excedido, 0 = Normal).
      - Registro 2: Total acumulado de entradas (IN).
      - Registro 3: Total acumulado de salidas (OUT).
      - Registro 4: Bandera de intrusión perimetral activa (1 = Activa, 0 = Inactiva).
      - Registro 5: Umbral de aforo máximo configurado (Límite).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        default_capacity_limit: int = 50
    ):
        self.host = host or os.getenv("MODBUS_HOST", "0.0.0.0")
        self.port = port or int(os.getenv("MODBUS_PORT", "5020"))
        self.capacity_limit = default_capacity_limit
        
        # Bloque de 100 registros con valores iniciales
        initial_registers = [0] * 100
        initial_registers[5] = self.capacity_limit  # Registro 5: Límite
        
        datablock = ModbusSequentialDataBlock(0, initial_registers)
        self.store = ModbusSlaveContext(
            di=datablock,
            co=datablock,
            hr=datablock,
            ir=datablock
        )
        self.context = ModbusServerContext(slaves=self.store, single=True)
        
        self._server: Optional[ModbusTcpServer] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_running = False

    def start(self) -> None:
        """Inicia el servidor Modbus TCP en un hilo asíncrono dedicado."""
        if self._is_running:
            return
            
        self._thread = threading.Thread(
            target=self._run_server_loop,
            daemon=True,
            name="Modbus-TCP-Server"
        )
        self._thread.start()
        logger.info(f"Servidor Modbus TCP configurado en {self.host}:{self.port}.")

    def _run_server_loop(self) -> None:
        """Bucle de eventos asyncio para el servidor Modbus."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        async def serve():
            try:
                self._server = ModbusTcpServer(
                    context=self.context,
                    address=(self.host, self.port)
                )
                self._is_running = True
                logger.info(f"Servidor Modbus TCP escuchando activamente en puerto {self.port}...")
                await self._server.serve_forever()
            except Exception as e:
                logger.error(f"Error en servidor Modbus TCP: {str(e)}", exc_info=True)
            finally:
                self._is_running = False

        self._loop.run_until_complete(serve())

    def update_occupancy(self, in_count: int, out_count: int) -> None:
        """
        Actualiza los registros Modbus con los valores de conteo actuales.
        Si la ocupación supera el límite, escribe 1 en el Holding Register 1.
        """
        try:
            occupancy = max(0, in_count - out_count)
            # Leer límite actual del registro 5 en caso de haber sido modificado por el PLC
            current_limit = self.store.getValues(3, 5, count=1)[0]
            if current_limit > 0:
                self.capacity_limit = current_limit

            # Registro 1 = 1 si se supera el límite de aforo, 0 en caso contrario
            is_over_capacity = 1 if occupancy >= self.capacity_limit else 0

            # Escribir registros holding (Función Modbus 3/6/16)
            # Reg 0: Ocupación, Reg 1: Alarma Sobre-aforo, Reg 2: IN, Reg 3: OUT
            self.store.setValues(3, 0, [
                int(occupancy) & 0xFFFF,
                int(is_over_capacity) & 0xFFFF,
                int(in_count) & 0xFFFF,
                int(out_count) & 0xFFFF
            ])
            
            if is_over_capacity == 1:
                logger.warning(f"[MODBUS] ¡Aforo excedido! Registro 1 establecido en 1 (Ocupación: {occupancy}/{self.capacity_limit}).")

        except Exception as e:
            logger.error(f"Error actualizando registros Modbus: {str(e)}")

    def set_intrusion_alarm(self, active: bool) -> None:
        """Activa o desactiva la bandera de intrusión perimetral en el Registro 4."""
        try:
            flag_val = 1 if active else 0
            self.store.setValues(3, 4, [flag_val])
        except Exception as e:
            logger.error(f"Error actualizando alarma de intrusión en Modbus: {str(e)}")

    def stop(self) -> None:
        """Detiene el servidor Modbus TCP."""
        self._is_running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("Servidor Modbus TCP detenido.")
