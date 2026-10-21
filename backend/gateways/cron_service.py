# ==============================================================================
# CASVMS - Internal Midnight Cron Service (Zero-Polling Daemon)
# ==============================================================================
import time
import logging
import threading
from datetime import datetime, timedelta
from multiprocessing.synchronize import Event as MpEvent
from typing import Callable, Optional, List

logger = logging.getLogger("CASVMS.Cron")

class MidnightResetCron:
    """
    Hilo daemon que ejecuta el reset de contadores de aforo e I/O a medianoche (00:00:00).
    Calcula el tiempo delta exacto hasta la próxima medianoche y utiliza sincronización
    basada en eventos sin consumo de ciclos de CPU (cero polling).
    """

    def __init__(
        self,
        reset_events: List[MpEvent],
        on_reset_callback: Optional[Callable[[], None]] = None
    ):
        self.reset_events = reset_events
        self.on_reset_callback = on_reset_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia el hilo daemon del cron."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="Midnight-Cron-Daemon"
        )
        self._thread.start()
        logger.info("Servicio de Cron Interno para reset a medianoche iniciado.")

    def _seconds_until_midnight(self) -> float:
        """Calcula los segundos exactos restantes hasta la próxima medianoche local."""
        now = datetime.now()
        tomorrow_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        diff = (tomorrow_midnight - now).total_seconds()
        # Asegurar al menos 1 segundo
        return max(1.0, diff)

    def _run_loop(self) -> None:
        """Bucle principal de espera pasiva hasta medianoche."""
        while not self._stop_event.is_set():
            wait_time = self._seconds_until_midnight()
            hours = wait_time / 3600.0
            logger.info(f"Cron programado: Próximo reset de aforo en {hours:.2f} horas ({wait_time:.1f} segundos).")

            # Espera sin consumo de CPU; se interrumpe inmediatamente si se solicita parada
            interrupted = self._stop_event.wait(timeout=wait_time)
            
            if interrupted or self._stop_event.is_set():
                break

            # Disparo a las 00:00:00
            logger.info(">>> [CRON] Medianoche alcanzada (00:00:00). Ejecutando reset de aforo y registros I/O...")
            
            # 1. Notificar a los procesos hijos de las cámaras vía multiprocessing.Event
            for event in self.reset_events:
                try:
                    event.set()
                except Exception as e:
                    logger.error(f"Error activando evento de reset en proceso hijo: {e}")

            # 2. Invocar callback para gateways (Modbus, InfluxDB, etc.)
            if self.on_reset_callback:
                try:
                    self.on_reset_callback()
                except Exception as cb_err:
                    logger.error(f"Error ejecutando callback de reset a medianoche: {cb_err}")

            # Pequeña pausa de 2 segundos para superar el segundo 00 y evitar doble disparo
            time.sleep(2.0)

    def stop(self) -> None:
        """Detiene el servicio de cron."""
        self._stop_event.set()
        logger.info("Servicio de Cron Interno detenido.")
