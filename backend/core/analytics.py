# ==============================================================================
# CASVMS - Vector Math & Behavioral Analytics Engine
# ==============================================================================
import time
import math
import uuid
import logging
from typing import List, Dict, Tuple, Optional, Set
import numpy as np
import cv2

from core.types import (
    Point2D,
    TrackedDetection,
    TripwireConfig,
    ZoneConfig,
    CrowdConfig,
    AlertEvent,
    RuleType,
    Severity
)

logger = logging.getLogger("CASVMS.Analytics")

class VectorAnalyticsEngine:
    """
    Motor analítico espacial de alta eficiencia computacional.
    
    Implementa:
    1. Cruce direccional de líneas virtuales (Tripwire IN/OUT) mediante orientación CCW.
    2. Detección de intrusión y permanencia excesiva (Dwell/Parking time) vía pointPolygonTest.
    3. Agrupación y detección de multitudes (Crowd Gathering) basada en distancias euclidianas.
    """

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        
        # Historial de posiciones anteriores de cada track: {track_id: (foot_point, timestamp)}
        self._track_history: Dict[int, Tuple[Point2D, float]] = {}
        
        # Registro de tiempos de entrada para zonas poligonales: {(track_id, rule_id): entry_timestamp}
        self._dwell_tracker: Dict[Tuple[int, str], float] = {}
        
        # Registro de cruces de líneas para evitar rebotes o conteos duplicados: {(track_id, rule_id): last_cross_time}
        self._tripwire_cooldown: Dict[Tuple[int, str], float] = {}
        
        # Contadores acumulados de aforo
        self.in_count: int = 0
        self.out_count: int = 0

    @staticmethod
    def _ccw(a: Point2D, b: Point2D, c: Point2D) -> bool:
        """
        Predicado de orientación: determina si el trío de puntos (A, B, C)
        está orientado en sentido antihorario (Counter-Clockwise).
        """
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    @classmethod
    def segments_intersect(cls, p1: Point2D, p2: Point2D, a: Point2D, b: Point2D) -> bool:
        """
        Determina si el segmento de movimiento [P1, P2] se cruza con el segmento [A, B].
        """
        return (cls._ccw(p1, a, b) != cls._ccw(p2, a, b)) and (cls._ccw(p1, p2, a) != cls._ccw(p1, p2, b))

    @staticmethod
    def _compute_crossing_direction(p1: Point2D, p2: Point2D, a: Point2D, b: Point2D) -> str:
        """
        Calcula si el cruce del vector [P1 -> P2] a través de la línea [A -> B]
        es de entrada ('IN') o salida ('OUT') utilizando el producto vectorial 2D.
        """
        # Vector de la línea virtual: V = B - A
        vx = b[0] - a[0]
        vy = b[1] - a[1]
        
        # Vector de movimiento del objeto: D = P2 - P1
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        
        # Producto cruz en 2D: Vx * Dy - Vy * Dx
        cross_product = (vx * dy) - (vy * dx)
        return "IN" if cross_product > 0 else "OUT"

    def process_tripwires(
        self,
        detections: List[TrackedDetection],
        tripwires: List[TripwireConfig],
        current_time: float
    ) -> List[AlertEvent]:
        """
        Evalúa el cruce de líneas virtuales direccionales.
        """
        alerts: List[AlertEvent] = []
        
        for det in detections:
            if det.track_id < 0:
                continue

            current_pos = det.foot_point
            prev_entry = self._track_history.get(det.track_id)
            
            if prev_entry is None:
                continue

            prev_pos, _ = prev_entry
            
            # Verificar si el objeto se ha movido
            if prev_pos == current_pos:
                continue

            for tw in tripwires:
                if not tw.enabled:
                    continue
                if tw.target_classes and det.class_name not in tw.target_classes:
                    continue

                cooldown_key = (det.track_id, tw.rule_id)
                last_crossed = self._tripwire_cooldown.get(cooldown_key, 0.0)
                if current_time - last_crossed < 2.0:
                    # Cooldown de 2 segundos para evitar conteos repetidos
                    continue

                if self.segments_intersect(prev_pos, current_pos, tw.pt1, tw.pt2):
                    direction = self._compute_crossing_direction(prev_pos, current_pos, tw.pt1, tw.pt2)
                    self._tripwire_cooldown[cooldown_key] = current_time
                    
                    if direction == "IN":
                        self.in_count += 1
                    else:
                        self.out_count += 1

                    alert = AlertEvent(
                        alert_id=str(uuid.uuid4()),
                        camera_id=self.camera_id,
                        rule_id=tw.rule_id,
                        rule_type=RuleType.TRIPWIRE,
                        severity=Severity.INFO,
                        timestamp=current_time,
                        message=f"Cruce de línea '{tw.name}' detectado: {det.class_name} ({direction})",
                        metadata={
                            "direction": direction,
                            "track_id": det.track_id,
                            "class": det.class_name,
                            "in_count": self.in_count,
                            "out_count": self.out_count
                        }
                    )
                    alerts.append(alert)
                    logger.info(f"[{self.camera_id}] Cruce {direction} en tripwire {tw.name} por ID={det.track_id}")

        return alerts

    def process_zones(
        self,
        detections: List[TrackedDetection],
        zones: List[ZoneConfig],
        current_time: float
    ) -> List[AlertEvent]:
        """
        Evalúa intrusiones y exceso de permanencia (Dwell Time / Parking) en zonas poligonales.
        """
        alerts: List[AlertEvent] = []
        active_zone_tracks: Set[Tuple[int, str]] = set()

        for zone in zones:
            if not zone.enabled or len(zone.polygon) < 3:
                continue

            # Conversión del polígono a formato NumPy int32/float32 para cv2.pointPolygonTest
            pts_array = np.array(zone.polygon, dtype=np.float32).reshape((-1, 1, 2))

            for det in detections:
                if det.track_id < 0:
                    continue
                if zone.target_classes and det.class_name not in zone.target_classes:
                    continue

                foot_x, foot_y = det.foot_point
                # measureDist=False: retorna +1 (dentro), -1 (fuera), 0 (borde)
                inside = cv2.pointPolygonTest(pts_array, (float(foot_x), float(foot_y)), False) >= 0

                if inside:
                    zone_key = (det.track_id, zone.rule_id)
                    active_zone_tracks.add(zone_key)
                    
                    # Registrar primera detección dentro de la zona
                    if zone_key not in self._dwell_tracker:
                        self._dwell_tracker[zone_key] = current_time

                        # Si la regla es intrusión inmediata:
                        if zone.rule_type == RuleType.INTRUSION:
                            alerts.append(AlertEvent(
                                alert_id=str(uuid.uuid4()),
                                camera_id=self.camera_id,
                                rule_id=zone.rule_id,
                                rule_type=RuleType.INTRUSION,
                                severity=Severity.HIGH,
                                timestamp=current_time,
                                message=f"Intrusión en zona restringida '{zone.name}': {det.class_name} (ID {det.track_id})",
                                metadata={
                                    "track_id": det.track_id,
                                    "class": det.class_name,
                                    "zone": zone.name
                                }
                            ))
                    else:
                        # Si es control de permanencia/parking
                        dwell_duration = current_time - self._dwell_tracker[zone_key]
                        if zone.rule_type == RuleType.DWELL_TIME and dwell_duration >= zone.max_dwell_seconds:
                            # Disparar alerta con severidad proporcional al exceso
                            alerts.append(AlertEvent(
                                alert_id=str(uuid.uuid4()),
                                camera_id=self.camera_id,
                                rule_id=zone.rule_id,
                                rule_type=RuleType.DWELL_TIME,
                                severity=Severity.WARNING,
                                timestamp=current_time,
                                message=f"Permanencia/Parking excesivo en '{zone.name}': {dwell_duration:.1f}s (Límite: {zone.max_dwell_seconds}s)",
                                metadata={
                                    "track_id": det.track_id,
                                    "class": det.class_name,
                                    "dwell_seconds": dwell_duration,
                                    "zone": zone.name
                                }
                            ))

        # Limpieza de objetos que abandonaron las zonas
        stale_keys = [k for k in self._dwell_tracker.keys() if k not in active_zone_tracks]
        for k in stale_keys:
            del self._dwell_tracker[k]

        return alerts

    def process_crowd(
        self,
        detections: List[TrackedDetection],
        crowd_config: Optional[CrowdConfig],
        current_time: float
    ) -> List[AlertEvent]:
        """
        Detección de aglomeraciones de personas mediante matriz de distancias euclidianas.
        """
        if not crowd_config or not crowd_config.enabled:
            return []

        # Filtrar exclusivamente personas con ID válido o detección confirmada
        persons = [d for d in detections if d.class_name == "person"]
        if len(persons) < crowd_config.min_people:
            return []

        try:
            # Extraer coordenadas base de todas las personas
            coords = np.array([p.foot_point for p in persons], dtype=np.float32)
            
            # Matriz de distancias euclidianas por pares: shape (N, N)
            diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
            dist_matrix = np.sqrt(np.sum(diff ** 2, axis=-1))

            # Matriz de adyacencia según el umbral de proximidad
            adjacency = dist_matrix <= crowd_config.proximity_threshold_px
            
            # Algoritmo de componentes conectados mediante BFS para encontrar conglomerados
            n_people = len(persons)
            visited = np.zeros(n_people, dtype=bool)
            clusters: List[List[int]] = []

            for i in range(n_people):
                if not visited[i]:
                    cluster: List[int] = []
                    queue = [i]
                    visited[i] = True
                    
                    while queue:
                        curr = queue.pop(0)
                        cluster.append(curr)
                        neighbors = np.where(adjacency[curr] & ~visited)[0]
                        for neighbor in neighbors:
                            visited[neighbor] = True
                            queue.append(neighbor)
                            
                    if len(cluster) >= crowd_config.min_people:
                        clusters.append(cluster)

            alerts: List[AlertEvent] = []
            for cluster_indices in clusters:
                cluster_coords = coords[cluster_indices]
                centroid_x = float(np.mean(cluster_coords[:, 0]))
                centroid_y = float(np.mean(cluster_coords[:, 1]))
                crowd_size = len(cluster_indices)

                alert = AlertEvent(
                    alert_id=str(uuid.uuid4()),
                    camera_id=self.camera_id,
                    rule_id=crowd_config.rule_id,
                    rule_type=RuleType.CROWD,
                    severity=Severity.HIGH if crowd_size >= (crowd_config.min_people * 1.5) else Severity.WARNING,
                    timestamp=current_time,
                    message=f"Aglomeración de personas detectada: {crowd_size} individuos agrupados.",
                    metadata={
                        "crowd_count": crowd_size,
                        "centroid": (centroid_x, centroid_y),
                        "member_track_ids": [persons[idx].track_id for idx in cluster_indices]
                    }
                )
                alerts.append(alert)

            return alerts

        except Exception as e:
            logger.error(f"Error en análisis de aglomeración de multitudes: {str(e)}", exc_info=True)
            return []

    def update_tracks(self, detections: List[TrackedDetection], current_time: float) -> None:
        """
        Actualiza el mapa histórico de posiciones para el siguiente fotograma y purga tracks obsoletos.
        """
        active_ids = set()
        for det in detections:
            if det.track_id >= 0:
                active_ids.add(det.track_id)
                self._track_history[det.track_id] = (det.foot_point, current_time)

        # Purgar tracks que no se hayan visto en más de 5 segundos
        stale_track_ids = [
            tid for tid, (_, t_seen) in self._track_history.items()
            if (current_time - t_seen > 5.0) and (tid not in active_ids)
        ]
        for tid in stale_track_ids:
            del self._track_history[tid]

    def reset_counts(self) -> None:
        """Reinicia los contadores de aforo acumulados (ej. a medianoche)."""
        self.in_count = 0
        self.out_count = 0
        logger.info(f"Contadores de aforo para cámara {self.camera_id} reseteados a 0.")
