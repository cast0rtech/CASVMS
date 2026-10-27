// ==============================================================================
// CASVMS - Native Tauri FS, Dialog & Notification Integration
// ==============================================================================
import { Camera } from "../types/vms";

const CONFIG_FILE_NAME = "casvms_rules_config.json";

function isTauri(): boolean {
  return typeof window !== "undefined" && (window as any).__TAURI__ !== undefined;
}

/**
 * Guarda la configuración completa de cámaras y reglas en $APPCONFIG.
 * El frontend actúa como fuente de la verdad (Source of Truth).
 */
export async function saveConfigToAppConfig(cameras: Camera[]): Promise<boolean> {
  const jsonContent = JSON.stringify(cameras, null, 2);

  if (isTauri()) {
    try {
      const { writeTextFile, BaseDirectory } = await import("@tauri-apps/api/fs");
      await writeTextFile(CONFIG_FILE_NAME, jsonContent, {
        dir: BaseDirectory.AppConfig
      });
      console.log("[Tauri FS] Configuración guardada en $APPCONFIG.");
      return true;
    } catch (err) {
      console.error("[Tauri FS] Error guardando configuración:", err);
      return false;
    }
  } else {
    // Fallback a LocalStorage para desarrollo web
    localStorage.setItem(CONFIG_FILE_NAME, jsonContent);
    return true;
  }
}

/**
 * Carga la configuración desde $APPCONFIG.
 */
export async function loadConfigFromAppConfig(): Promise<Camera[] | null> {
  if (isTauri()) {
    try {
      const { readTextFile, BaseDirectory } = await import("@tauri-apps/api/fs");
      const content = await readTextFile(CONFIG_FILE_NAME, {
        dir: BaseDirectory.AppConfig
      });
      return JSON.parse(content);
    } catch (err) {
      console.warn("[Tauri FS] Archivo en $APPCONFIG no encontrado o inválido.");
      return null;
    }
  } else {
    const item = localStorage.getItem(CONFIG_FILE_NAME);
    return item ? JSON.parse(item) : null;
  }
}

/**
 * Exporta la configuración JSON a un pendrive USB o ubicación seleccionada mediante tauri/api/dialog.
 */
export async function exportConfigToDisk(cameras: Camera[]): Promise<boolean> {
  const jsonContent = JSON.stringify(cameras, null, 2);

  if (isTauri()) {
    try {
      const { save } = await import("@tauri-apps/api/dialog");
      const { writeTextFile } = await import("@tauri-apps/api/fs");

      const selectedPath = await save({
        title: "Exportar Configuración CASVMS a Pendrive",
        defaultPath: "casvms_backup.json",
        filters: [{ name: "JSON Config", extensions: ["json"] }]
      });

      if (selectedPath) {
        await writeTextFile(selectedPath, jsonContent);
        return true;
      }
      return false;
    } catch (err) {
      console.error("[Tauri Dialog] Error exportando configuración:", err);
      return false;
    }
  } else {
    // Fallback en navegador mediante descarga de blob
    const blob = new Blob([jsonContent], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "casvms_backup.json";
    a.click();
    URL.revokeObjectURL(url);
    return true;
  }
}

/**
 * Importa configuración JSON desde archivo local o pendrive físico.
 */
export async function importConfigFromDisk(): Promise<Camera[] | null> {
  if (isTauri()) {
    try {
      const { open } = await import("@tauri-apps/api/dialog");
      const { readTextFile } = await import("@tauri-apps/api/fs");

      const selected = await open({
        multiple: false,
        filters: [{ name: "JSON Config", extensions: ["json"] }]
      });

      if (typeof selected === "string") {
        const text = await readTextFile(selected);
        return JSON.parse(text);
      }
      return null;
    } catch (err) {
      console.error("[Tauri Dialog] Error importando configuración:", err);
      return null;
    }
  } else {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".json";
      input.onchange = async (e: any) => {
        const file = e.target.files?.[0];
        if (file) {
          const text = await file.text();
          resolve(JSON.parse(text));
        } else {
          resolve(null);
        }
      };
      input.click();
    });
  }
}

/**
 * Exporta un clip de vídeo MP4 nativamente al destino que elija el usuario (USB, Descargas).
 */
export async function exportVideoClipNative(
  sourcePath: string,
  suggestedFilename: string
): Promise<boolean> {
  if (isTauri()) {
    try {
      const { save } = await import("@tauri-apps/api/dialog");
      const { copyFile } = await import("@tauri-apps/api/fs");

      const destPath = await save({
        title: "Guardar Clip MP4 en Pendrive / Disco",
        defaultPath: suggestedFilename,
        filters: [{ name: "Vídeo MP4", extensions: ["mp4"] }]
      });

      if (destPath) {
        await copyFile(sourcePath, destPath);
        return true;
      }
      return false;
    } catch (err) {
      console.error("[Tauri FS] Fallo al copiar clip MP4 nativamente:", err);
      return false;
    }
  } else {
    // Si corre en web, descargar mediante enlace directo
    const a = document.createElement("a");
    a.href = `http://localhost:8001/api/recordings/${encodeURIComponent(suggestedFilename)}`;
    a.download = suggestedFilename;
    a.click();
    return true;
  }
}

/**
 * Notificación nativa de escritorio de Tauri para alarmas de alta severidad.
 */
export async function triggerNativeAlertNotification(title: string, body: string): Promise<void> {
  if (isTauri()) {
    try {
      const {
        isPermissionGranted,
        requestPermission,
        sendNotification
      } = await import("@tauri-apps/api/notification");

      let hasPermission = await isPermissionGranted();
      if (!hasPermission) {
        const permission = await requestPermission();
        hasPermission = permission === "granted";
      }

      if (hasPermission) {
        sendNotification({ title, body });
      }
    } catch (err) {
      console.warn("Error mostrando notificación nativa:", err);
    }
  } else if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}
