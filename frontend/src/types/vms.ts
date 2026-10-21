export type Point2D = [number, number];

export type Severity = "info" | "warning" | "high" | "critical";

export type RuleType = "tripwire" | "intrusion" | "dwell_time" | "crowd" | "access_control";

export interface AuthorizedPlate {
  id: number;
  plate_number: string;
  normalized_plate: string;
  owner_name: string;
  vehicle_model: string;
  is_active: number;
  created_at: string;
}

export interface TripwireRule {
  rule_id: string;
  name: string;
  pt1: Point2D;
  pt2: Point2D;
  target_classes: string[];
  enabled: boolean;
}

export interface ZoneRule {
  rule_id: string;
  name: string;
  polygon: Point2D[];
  rule_type: RuleType;
  max_dwell_seconds: number;
  target_classes: string[];
  enabled: boolean;
}

export interface CameraRules {
  tripwires: TripwireRule[];
  zones: ZoneRule[];
}

export interface Camera {
  id: string;
  name: string;
  rtsp_url: string;
  is_alive: boolean;
  pid?: number;
  rules: CameraRules;
  telemetry?: {
    fps: number;
    in_count: number;
    out_count: number;
    active_occupancy: number;
    active_tracks: number;
    motion_detected: boolean;
    is_standby: boolean;
  };
}

export interface AlertEvent {
  alert_id: string;
  camera_id: string;
  rule_id: string;
  rule_type: RuleType;
  severity: Severity;
  timestamp: number;
  message: string;
  metadata?: Record<string, any>;
}

export interface RecordingClip {
  filename: string;
  filepath: string;
  size_bytes: number;
  size_mb: number;
  created_at: number;
  metadata?: {
    camera_id?: string;
    rule_name?: string;
    total_frames?: number;
    duration_seconds?: number;
    fps?: number;
    resolution?: string;
    created_at?: number;
  };
}

export interface SystemTelemetry {
  timestamp: number;
  total_in: number;
  total_out: number;
  total_occupancy: number;
  cameras: Record<string, any>;
  recent_alerts_count: number;
}
