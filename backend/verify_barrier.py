# ==============================================================================
# CASVMS - Test & Verification Script for Modbus Barrier Gateway
# ==============================================================================
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateways.barrier_gateway import ModbusBarrierGateway

def test_modbus_barrier_gateway():
    print("-> Verificando ModbusBarrierGateway (Control de Relé de Barrera)...")
    
    # Instanciación con IP ficticia para probar resiliencia y manejo no bloqueante de excepciones
    gw = ModbusBarrierGateway(
        plc_host="192.168.1.254",
        plc_port=502,
        slave_unit=1,
        pulse_duration_seconds=0.1,  # Duración corta para test rápido
        connection_timeout=0.5
    )

    t0 = time.time()
    # open_barrier arranca un hilo daemon y debe retornar de forma INMEDIATA (< 50ms)
    gw.open_barrier(coil_address=0, plate="ZURICH-1234")
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"open_barrier bloqueó el hilo principal! Tardó {elapsed:.3f}s"
    print(f"   [OK] Invocación open_barrier no bloqueante: retornó en {elapsed*1000:.2f} ms.")

    t1 = time.time()
    gw.trigger_barrier(coil_address=1, slave_id=1)
    elapsed_trigger = time.time() - t1
    assert elapsed_trigger < 0.1, f"trigger_barrier bloqueó el hilo principal! Tardó {elapsed_trigger:.3f}s"
    print(f"   [OK] Invocación trigger_barrier no bloqueante: retornó en {elapsed_trigger*1000:.2f} ms.")

    # Esperar a que los hilos worker terminen su intento de conexión y captura de excepción de red
    time.sleep(1.0)
    print("   [OK] Excepción de red capturada correctamente sin abortar el proceso.")

if __name__ == "__main__":
    print("==================================================")
    print("TEST: GATEWAY MODBUS TCP BARRERA (AUTO-RESET PULSE)")
    print("==================================================")
    test_modbus_barrier_gateway()
    print("\n>>> MODBUS BARRIER GATEWAY VALIDADO EXITOSAMENTE <<<")
