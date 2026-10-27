// ==============================================================================
// CASVMS - Frontend REST & SSE API Client
// ==============================================================================
import {
  Camera,
  AlertEvent,
  RecordingClip,
  SystemTelemetry,
  AuthorizedPlate,
  ModbusConfig,
  ModbusStatus,
  ONVIFDevice
} from "../types/vms";

export const API_BASE = "http://localhost:8001";

export async function fetchCameras(): Promise<Camera[]> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("Fallo conectando a backend FastAPI:", err);
    return [];
  }
}

export async function fetchTelemetry(): Promise<SystemTelemetry | null> {
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return null;
  }
}

export async function fetchRecordings(): Promise<RecordingClip[]> {
  try {
    const res = await fetch(`${API_BASE}/api/recordings`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("No se pudieron cargar grabaciones:", err);
    return [];
  }
}

export async function resetOccupancyCounts(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/system/reset-counts`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchALPRWhitelist(): Promise<AuthorizedPlate[]> {
  try {
    const res = await fetch(`${API_BASE}/api/alpr/whitelist`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.records)) return data.records;
    return [];
  } catch (err) {
    console.warn("Fallo obteniendo whitelist ALPR:", err);
    return [];
  }
}

export async function addALPRWhitelist(plate: string, owner: string = ""): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/alpr/whitelist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plate, owner })
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function deleteALPRWhitelist(plate: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/alpr/whitelist/${encodeURIComponent(plate)}`, {
      method: "DELETE"
    });
    return res.ok;
  } catch {
    return false;
  }
}

export const fetchAuthorizedPlates = fetchALPRWhitelist;
export const addAuthorizedPlate = addALPRWhitelist;
export const deleteAuthorizedPlate = deleteALPRWhitelist;



export function getStreamUrl(cameraId: string): string {
  return `${API_BASE}/stream/${cameraId}`;
}

export function getRecordingStreamUrl(filename: string): string {
  return `${API_BASE}/api/recordings/${encodeURIComponent(filename)}`;
}

export function subscribeAlertsSSE(
  onAlert: (alert: AlertEvent) => void,
  onError?: (err: any) => void
): () => void {
  const url = `${API_BASE}/api/alerts/sse`;
  let eventSource: EventSource | null = new EventSource(url);

  eventSource.addEventListener("alert", (event: MessageEvent) => {
    try {
      const data: AlertEvent = JSON.parse(event.data);
      onAlert(data);
    } catch (parseErr) {
      console.error("Error parseando alerta SSE:", parseErr);
    }
  });

  eventSource.onerror = (err) => {
    if (onError) onError(err);
  };

  // Retorna función para desuscribirse limpiamente
  return () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  };
}

// ==========================================
// Camera Management & Import API
// ==========================================

export async function saveCamera(camera: Partial<Camera>): Promise<{ success: boolean; camera?: Camera; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(camera),
    });
    const data = await res.json();
    return { success: res.ok, camera: data.camera, error: data.detail || data.error };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

export async function deleteCamera(id: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function importCameras(payload: {
  cameras?: Partial<Camera>[];
  csv_text?: string;
  replace_all?: boolean;
}): Promise<{ success: boolean; count?: number; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    return { success: res.ok, count: data.count, error: data.detail || data.error };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

export async function discoverONVIFCameras(): Promise<ONVIFDevice[]> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras/discover-onvif`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeout: 3.0 }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.devices || [];
  } catch (err) {
    console.warn("Error en escaneo ONVIF:", err);
    return [];
  }
}

export async function testCameraStream(rtspUrl: string): Promise<{
  success: boolean;
  fps?: number;
  resolution?: string;
  error?: string;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/cameras/test-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rtsp_url: rtspUrl, timeout_seconds: 4.0 }),
    });
    const data = await res.json();
    return {
      success: !!data.reachable,
      fps: data.fps,
      resolution: data.resolution,
      error: data.error,
    };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

// ==========================================
// Modbus Industrial Gateway API
// ==========================================

export async function fetchModbusConfig(): Promise<ModbusConfig | null> {
  try {
    const res = await fetch(`${API_BASE}/api/modbus/config`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.config || null;
  } catch (err) {
    console.warn("Fallo obteniendo configuración Modbus:", err);
    return null;
  }
}

export async function saveModbusConfig(config: Partial<ModbusConfig>): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/modbus/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchModbusStatus(): Promise<ModbusStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/api/modbus/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return null;
  }
}

export async function testModbusOutput(params: {
  output_key?: string;
  coil_address?: number;
  pulse_duration?: number;
  is_direct_coil?: boolean;
}): Promise<{ success: boolean; message: string; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/modbus/test-output`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    const data = await res.json();
    return {
      success: res.ok && data.status === "success",
      message: data.message || "OK",
      error: data.detail || data.error,
    };
  } catch (err: any) {
    return { success: false, message: "Error de red", error: err.message };
  }
}
