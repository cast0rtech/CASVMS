# ==============================================================================
# CASVMS Core AI & Analytics Package
# ==============================================================================
from core.types import (
    Point2D,
    TrackedDetection,
    TripwireConfig,
    ZoneConfig,
    CrowdConfig,
    AlertEvent,
    TelemetryData,
    Severity,
    RuleType
)
try:
    from core.motion import MotionGatekeeper
except ImportError:
    MotionGatekeeper = None

try:
    from core.detector import EdgeYOLODetector
except ImportError:
    EdgeYOLODetector = None

try:
    from core.analytics import VectorAnalyticsEngine
except ImportError:
    VectorAnalyticsEngine = None

try:
    from core.dvr import SmartRAMDVR
except ImportError:
    SmartRAMDVR = None

from core.plate_whitelist import PlateWhitelistManager, ALPRWhitelistDB

try:
    from core.alpr import ALPRPipeline, VEHICLE_CLASSES, process_alpr_crop, extract_vehicle_crop
except ImportError:
    ALPRPipeline = None
    VEHICLE_CLASSES = None
    process_alpr_crop = None
    extract_vehicle_crop = None

__all__ = [
    "Point2D",
    "TrackedDetection",
    "TripwireConfig",
    "ZoneConfig",
    "CrowdConfig",
    "AlertEvent",
    "TelemetryData",
    "Severity",
    "RuleType",
    "MotionGatekeeper",
    "EdgeYOLODetector",
    "VectorAnalyticsEngine",
    "SmartRAMDVR",
    "PlateWhitelistManager",
    "ALPRWhitelistDB",
    "ALPRPipeline",
    "VEHICLE_CLASSES",
    "process_alpr_crop",
    "extract_vehicle_crop"
]

