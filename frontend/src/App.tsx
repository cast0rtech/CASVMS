import React, { useState, useEffect } from "react";
import { Camera, AlertEvent, SystemTelemetry } from "./types/vms";
import {
  fetchCameras,
  fetchTelemetry,
  subscribeAlertsSSE,
  resetOccupancyCounts,
  API_BASE
} from "./services/api";
import {
  loadConfigFromAppConfig,
  saveConfigToAppConfig,
  exportConfigToDisk,
  importConfigFromDisk,
  triggerNativeAlertNotification
} from "./services/tauriStorage";

import { Header } from "./components/Header";
import { LiveGrid } from "./components/LiveGrid";
import { RuleEditorCanvas } from "./components/RuleEditorCanvas";
import { AlertPanel } from "./components/AlertPanel";
import { VideoGallery } from "./components/VideoGallery";
import { ALPRAccessPanel } from "./components/ALPRAccessPanel";
import { ConfigurationPanel } from "./components/ConfigurationPanel";

export const App: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [currentTab, setCurrentTab] = useState<"live" | "rules" | "gallery" | "alpr" | "config">("live");
  const [isAlertPanelOpen, setIsAlertPanelOpen] = useState<boolean>(true);


  // 1. Inicialización y Carga de Configuración (Frontend = Fuente de la Verdad)
  useEffect(() => {
    const initConfig = async () => {
      // Intentar cargar desde el almacenamiento persistente de Tauri ($APPCONFIG)
      const localConfig = await loadConfigFromAppConfig();
      if (localConfig && localConfig.length > 0) {
        console.log("[CASVMS] Configuración cargada desde $APPCONFIG.");
        setCameras(localConfig);
        setSelectedCameraId(localConfig[0].id);
      } else {
        // Fallback al backend
        const remoteCameras = await fetchCameras();
        if (remoteCameras.length > 0) {
          setCameras(remoteCameras);
          setSelectedCameraId(remoteCameras[0].id);
          // Persistir en $APPCONFIG
          await saveConfigToAppConfig(remoteCameras);
        }
      }
    };

    initConfig();
  }, []);

  // 2. Suscripción a Server-Sent Events (SSE) para Alertas en Tiempo Real
  useEffect(() => {
    const unsubscribe = subscribeAlertsSSE((newAlert) => {
      setAlerts((prev) => [newAlert, ...prev.slice(0, 99)]);

      // Notificación nativa de escritorio si es de severidad HIGH o CRITICAL
      if (newAlert.severity === "high" || newAlert.severity === "critical") {
        triggerNativeAlertNotification(
          `¡ALARMA PERIMETRAL! [${newAlert.camera_id}]`,
          newAlert.message
        );
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // 3. Polling de Telemetría cada 2 segundos
  useEffect(() => {
    const interval = setInterval(async () => {
      const data = await fetchTelemetry();
      if (data) setTelemetry(data);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  // Guardado de Reglas Vectoriales (Canvas)
  const handleSaveRules = async (updatedCamera: Camera) => {
    const updatedList = cameras.map((c) =>
      c.id === updatedCamera.id ? updatedCamera : c
    );
    setCameras(updatedList);
    setEditingCamera(null);

    // Guardar en Tauri FS ($APPCONFIG)
    await saveConfigToAppConfig(updatedList);

    // Sincronizar con backend FastAPI
    try {
      await fetch(`${API_BASE}/api/cameras/${updatedCamera.id}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedCamera.rules)
      });
    } catch (err) {
      console.warn("Backend no disponible para sincronización inmediata de reglas:", err);
    }
  };

  // Exportar configuración JSON a Pendrive
  const handleExportConfig = async () => {
    const ok = await exportConfigToDisk(cameras);
    if (ok) {
      alert("Configuración exportada con éxito al dispositivo.");
    }
  };

  // Importar configuración JSON desde Pendrive
  const handleImportConfig = async () => {
    const imported = await importConfigFromDisk();
    if (imported) {
      setCameras(imported);
      await saveConfigToAppConfig(imported);
      alert("Configuración importada y aplicada exitosamente.");
    }
  };

  // Reset de aforo manual
  const handleResetCounts = async () => {
    if (confirm("¿Deseas reiniciar los contadores de aforo diario (IN/OUT)?")) {
      await resetOccupancyCounts();
      const data = await fetchTelemetry();
      if (data) setTelemetry(data);
    }
  };

  const activeCam = cameras.find((c) => c.id === selectedCameraId) ?? cameras[0];

  return (
    <div className="flex flex-col h-screen w-screen bg-vms-darkest text-vms-text font-sans overflow-hidden">
      {/* Barra de Navegación Industrial */}
      <Header
        currentTab={currentTab}
        onTabChange={(tab) => {
          setCurrentTab(tab);
          if (tab !== "rules") setEditingCamera(null);
        }}
        telemetry={telemetry}
        onExportConfig={handleExportConfig}
        onImportConfig={handleImportConfig}
        onResetCounts={handleResetCounts}
        activeAlertCount={alerts.length}
      />

      {/* Espacio de Trabajo Principal */}
      <div className="flex-1 flex overflow-hidden">
        {/* Vistas en Vivo (Grid MJPEG) */}
        {currentTab === "live" && (
          <LiveGrid
            cameras={cameras}
            selectedCameraId={selectedCameraId}
            onSelectCamera={(id) => setSelectedCameraId(id)}
            onEditRules={(cam) => {
              setEditingCamera(cam);
              setCurrentTab("rules");
            }}
          />
        )}

        {/* Editor Vectorial de Reglas (Canvas Avanzado) */}
        {currentTab === "rules" && (
          editingCamera || activeCam ? (
            <RuleEditorCanvas
              camera={editingCamera || activeCam}
              onSaveRules={handleSaveRules}
              onClose={() => {
                setEditingCamera(null);
                setCurrentTab("live");
              }}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-vms-muted font-mono">
              Selecciona una cámara para editar sus reglas
            </div>
          )
        )}

        {/* Galería de Grabaciones (Smart DVR en Disco/Pendrive) */}
        {currentTab === "gallery" && <VideoGallery />}

        {/* Panel de Gestión de Accesos ALPR (Whitelist SQLite) */}
        {currentTab === "alpr" && <ALPRAccessPanel />}

        {/* Panel de Configuración General: Cámaras e Importación + Salidas Modbus TCP */}
        {currentTab === "config" && (
          <ConfigurationPanel
            onCamerasUpdated={(cams) => {
              setCameras(cams);
              saveConfigToAppConfig(cams);
            }}
          />
        )}

        {/* Panel de Alertas en Tiempo Real (Server-Sent Events) */}

        <AlertPanel
          alerts={alerts}
          onClearAlerts={() => setAlerts([])}
          isOpen={isAlertPanelOpen}
          onToggle={() => setIsAlertPanelOpen(!isAlertPanelOpen)}
        />
      </div>
    </div>
  );
};

export default App;
