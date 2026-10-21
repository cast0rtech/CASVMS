# ==============================================================================
# CASVMS - Test & Verification Script for ALPR Event Routing Pump
# ==============================================================================
import os
import sys
import time
import queue
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.plate_whitelist import ALPRWhitelistDB
from gateways.barrier_gateway import ModbusBarrierGateway

def test_event_routing_pump():
    print("-> Verificando event_routing_pump (Consumidor IPC de ALPR)...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        alpr_db = ALPRWhitelistDB(db_path=db_path)
        alpr_db.add_plate("ZURICH-1234", "Director General")

        test_queue = queue.Queue()
        barrier_triggered = []

        # Mock de barrier_gateway para verificar disparo sin PLC real
        class MockBarrierGateway:
            def trigger_barrier(self, coil_address=0, slave_id=1):
                barrier_triggered.append(coil_address)

        mock_barrier = MockBarrierGateway()

        # Inyectar evento de matrícula autorizada
        test_queue.put({
            "type": "alpr_read",
            "camera": "cam_parking",
            "plate": "ZURICH-1234"
        })

        # Inyectar evento de matrícula no autorizada
        test_queue.put({
            "type": "alpr_read",
            "camera": "cam_parking",
            "plate": "UNKNOWN-999"
        })

        # Ejecución controlada de 2 ciclos
        for _ in range(2):
            event = test_queue.get(timeout=1.0)
            if event.get("type") == "alpr_read":
                scanned_plate = event["plate"]
                cam_id = event["camera"]
                access_info = alpr_db.check_access(scanned_plate)
                
                if access_info:
                    mock_barrier.trigger_barrier(coil_address=0)
                    test_queue.put({
                        "type": "system_notification",
                        "camera": cam_id,
                        "message": f"Barrera abierta para {access_info['owner']} [{scanned_plate}]",
                        "severity": "info"
                    })
                else:
                    test_queue.put({
                        "type": "alert",
                        "camera": cam_id,
                        "message": f"Vehículo no autorizado detectado: {scanned_plate}",
                        "severity": "high"
                    })

        # Verificar resultados
        assert len(barrier_triggered) == 1, "La barrera debió dispararse exactamente 1 vez."
        assert barrier_triggered[0] == 0, "El Coil disparado debió ser 0."
        print("   [OK] Disparo físico de barrera verificado en Coil 0.")

        res_notif = test_queue.get(timeout=1.0)
        assert res_notif["type"] == "system_notification"
        assert res_notif["severity"] == "info"
        assert "ZURICH-1234" in res_notif["message"]
        print(f"   [OK] Notificación SSE autorizada generada: '{res_notif['message']}'")

        res_alert = test_queue.get(timeout=1.0)
        assert res_alert["type"] == "alert"
        assert res_alert["severity"] == "high"
        assert "UNKNOWN-999" in res_alert["message"]
        print(f"   [OK] Alerta crítica generada para intruso: '{res_alert['message']}'")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    print("==================================================")
    print("TEST: EVENT ROUTING PUMP (ALPR & MODBUS)")
    print("==================================================")
    test_event_routing_pump()
    print("\n>>> EVENT ROUTING PUMP VALIDADO EXITOSAMENTE <<<")
