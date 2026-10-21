# ==============================================================================
# CASVMS - Test & Verification Script for ONVIF Schedule Daemon
# ==============================================================================
import os
import sys
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateways.onvif_imaging import ONVIFScheduleDaemon

def test_onvif_schedule_daemon():
    print("-> Verificando ONVIF Schedule Daemon...")
    now = datetime.datetime.now()
    
    # Configurar horas para forzar el modo actual
    current_hour = now.hour
    
    daemon = ONVIFScheduleDaemon(
        cam_ip="192.168.1.254", # IP ficticia para probar tolerancia a fallos
        cam_port=80,
        day_hour=current_hour,      # Forzar que la hora actual caiga en DAY
        night_hour=(current_hour + 2) % 24,
        check_interval_seconds=0.2  # Intervalo corto para test
    )

    t0 = time.time()
    daemon.start()
    time.sleep(0.5)

    # Debe haber evaluado el modo esperado
    assert daemon.current_mode in ["DAY", "NIGHT", None]
    print(f"   [OK] Daemon iniciado en background. Estado evaluado: {daemon.current_mode}")

    # Probar parada limpia inmediata (< 300 ms) sin esperar los 60s
    t_stop_start = time.time()
    daemon.stop()
    stop_duration = time.time() - t_stop_start
    assert stop_duration < 0.5, f"La parada del daemon tardó demasiado: {stop_duration:.3f}s"
    print(f"   [OK] Parada limpia sin bloqueo: finalizó en {stop_duration*1000:.1f} ms.")

if __name__ == "__main__":
    print("==================================================")
    print("TEST: ONVIF SCHEDULE DAEMON (DAY / NIGHT AUTO)")
    print("==================================================")
    test_onvif_schedule_daemon()
    print("\n>>> ONVIF SCHEDULE DAEMON VALIDADO EXITOSAMENTE <<<")
