# ==============================================================================
# CASVMS - Test & Verification Script for Phase 2 Core Modules
# ==============================================================================
import sys
import time
import numpy as np
import cv2

from core.types import (
    Point2D,
    TrackedDetection,
    TripwireConfig,
    ZoneConfig,
    CrowdConfig,
    RuleType,
    Severity
)
from core.motion import MotionGatekeeper
from core.analytics import VectorAnalyticsEngine
from core.dvr import SmartRAMDVR

def test_gatekeeper():
    print("-> Verificando Gatekeeper MOG2...")
    gk = MotionGatekeeper(analysis_width=640, analysis_height=360, min_motion_area_px=500)
    
    # Frame 1: fondo negro
    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    raw_motion, is_standby, area, _ = gk.evaluate(black_frame)
    assert is_standby == True, "El Gatekeeper debería comenzar en standby sin movimiento"
    
    # Frame 2: introducción de un objeto brillante en movimiento
    motion_frame = black_frame.copy()
    cv2.rectangle(motion_frame, (300, 300), (600, 600), (255, 255, 255), -1)
    raw_motion, is_standby, area, _ = gk.evaluate(motion_frame)
    print(f"   [OK] MOG2 detectó movimiento: {raw_motion}, Standby: {is_standby}, Área: {area} px")

def test_vector_analytics():
    print("-> Verificando Motor Matemático Vectorial (CCW, Tripwire, Dwell, Crowd)...")
    engine = VectorAnalyticsEngine(camera_id="cam_test")
    
    # 1. Test CCW Intersect
    # Línea vertical de (100, 0) a (100, 200)
    # Movimiento horizontal de (50, 100) a (150, 100)
    p1 = (50.0, 100.0)
    p2 = (150.0, 100.0)
    a = (100.0, 0.0)
    b = (100.0, 200.0)
    assert engine.segments_intersect(p1, p2, a, b) == True, "Los segmentos deben intersectar"
    dir_cross = engine._compute_crossing_direction(p1, p2, a, b)
    assert dir_cross in ["IN", "OUT"], "Dirección de cruce debe ser IN u OUT"
    print(f"   [OK] CCW Intersect & Dirección: Cruce detectado como {dir_cross}")

    # 2. Test Tripwire
    tw = TripwireConfig(rule_id="tw1", name="Entrada Principal", pt1=a, pt2=b)
    det_prev = TrackedDetection(track_id=1, class_id=0, class_name="person", confidence=0.9, bbox=(40, 80, 60, 100))
    det_curr = TrackedDetection(track_id=1, class_id=0, class_name="person", confidence=0.9, bbox=(140, 80, 160, 100))
    
    now = time.time()
    engine.update_tracks([det_prev], now - 0.1)
    alerts = engine.process_tripwires([det_curr], [tw], now)
    assert len(alerts) == 1, "Debe generar exactamente una alerta de cruce"
    print(f"   [OK] Tripwire Alert generada: {alerts[0].message}")

    # 3. Test Zone Dwell / Intrusion
    poly = [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]
    zone = ZoneConfig(rule_id="z1", name="Zona Prohibida", polygon=poly, rule_type=RuleType.INTRUSION)
    det_in_zone = TrackedDetection(track_id=2, class_id=0, class_name="person", confidence=0.88, bbox=(50, 50, 70, 70))
    zone_alerts = engine.process_zones([det_in_zone], [zone], now)
    assert len(zone_alerts) == 1, "Debe generar alerta de intrusión"
    print(f"   [OK] Intrusión en Zona detectada: {zone_alerts[0].message}")

    # 4. Test Crowd Clustering
    crowd_cfg = CrowdConfig(rule_id="crowd_1", min_people=3, proximity_threshold_px=50.0)
    crowd_detections = [
        TrackedDetection(track_id=10, class_id=0, class_name="person", confidence=0.9, bbox=(10, 10, 20, 30)),
        TrackedDetection(track_id=11, class_id=0, class_name="person", confidence=0.9, bbox=(25, 15, 35, 35)),
        TrackedDetection(track_id=12, class_id=0, class_name="person", confidence=0.9, bbox=(30, 20, 40, 40)),
    ]
    crowd_alerts = engine.process_crowd(crowd_detections, crowd_cfg, now)
    assert len(crowd_alerts) == 1, "Debe agrupar las 3 personas en un clúster de multitud"
    print(f"   [OK] Aglomeración detectada: {crowd_alerts[0].message}")

def test_smart_dvr():
    print("-> Verificando Smart DVR en RAM (Búfer circular y exportador)...")
    dvr = SmartRAMDVR(
        camera_id="cam_test",
        storage_dir="/tmp/casvms_test_dvr",
        fps=10.0,
        pre_event_seconds=2,
        post_event_seconds=2,
        jpeg_quality=60
    )
    
    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.putText(dummy_frame, "TEST DVR", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # Llenar búfer con unos frames
    for i in range(10):
        dvr.push_frame(dummy_frame)
    
    assert len(dvr._pre_buffer) == 10, f"Búfer pre-evento debería tener 10 frames, tiene {len(dvr._pre_buffer)}"
    print(f"   [OK] Smart DVR comprimió y almacenó {len(dvr._pre_buffer)} frames JPEG en memoria RAM.")

if __name__ == "__main__":
    print("==================================================")
    print("EJECUTANDO BATERÍA DE COMPROBACIÓN FASE 1 & FASE 2")
    print("==================================================")
    try:
        test_gatekeeper()
        test_vector_analytics()
        test_smart_dvr()
        print("\n>>> TODAS LAS PRUEBAS DE LA FASE 2 HAN SIDO SUPERADAS EXITOSAMENTE <<<")
    except Exception as err:
        print(f"\n[ERROR EN COMPROBACIÓN]: {err}")
        sys.exit(1)
