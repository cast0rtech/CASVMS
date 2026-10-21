// ==============================================================================
// CASVMS - Frontend REST & SSE API Client
// ==============================================================================
import { Camera, AlertEvent, RecordingClip, SystemTelemetry, AuthorizedPlate } from "../types/vms";


export const API_BASE = "http://localhost:8000";

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
