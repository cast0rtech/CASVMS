# ==============================================================================
# CASVMS - Core Data Types and Protocols
# ==============================================================================
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Any, Optional
import time

Point2D = Tuple[float, float]

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"

class RuleType(str, Enum):
    TRIPWIRE = "tripwire"
    INTRUSION = "intrusion"
    DWELL_TIME = "dwell_time"
    CROWD = "crowd"

@dataclass
class TrackedDetection:
    """Representa un objeto detectado y rastreado por YOLO + ByteTrack."""
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    timestamp: float = field(default_factory=time.time)

    @property
    def foot_point(self) -> Point2D:
        """Punto base inferior (contacto con el suelo) para cálculos espaciales."""
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, float(y2))

    @property
    def centroid(self) -> Point2D:
        """Centro geométrico del bounding box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

@dataclass
class TripwireConfig:
    """Configuración de una línea virtual de cruce direccional."""
    rule_id: str
    name: str
    pt1: Point2D
    pt2: Point2D
    target_classes: List[str] = field(default_factory=lambda: ["person", "car", "truck"])
    enabled: bool = True

@dataclass
class ZoneConfig:
    """Configuración de un polígono de exclusión o zona de parking."""
    rule_id: str
    name: str
    polygon: List[Point2D]  # Lista ordenada de vértices en coordenadas normalizadas o de imagen
    rule_type: RuleType = RuleType.INTRUSION
    max_dwell_seconds: float = 30.0  # Umbral de tiempo para alerta de merodeo/parking
    target_classes: List[str] = field(default_factory=lambda: ["person", "car", "truck", "motorcycle"])
    enabled: bool = True

@dataclass
class CrowdConfig:
    """Configuración de detección de aglomeraciones por distancia euclidiana."""
    rule_id: str = "crowd_default"
    name: str = "Aglomeración de Personas"
    min_people: int = 5
    proximity_threshold_px: float = 120.0  # Distancia euclidiana máxima en píxeles entre pares
    enabled: bool = True

@dataclass
class AlertEvent:
    """Evento de alarma generado por el motor analítico."""
    alert_id: str
    camera_id: str
    rule_id: str
    rule_type: RuleType
    severity: Severity
    timestamp: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    snapshot_bytes: Optional[bytes] = None

@dataclass
class TelemetryData:
    """Métricas operativas y de aforo generadas por cada cámara."""
    camera_id: str
    timestamp: float
    in_count: int
    out_count: int
    active_occupancy: int
    active_tracks: int
    fps: float
    motion_detected: bool
    is_standby: bool
