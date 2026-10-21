import React, { useState } from "react";
import { Camera } from "../types/vms";
import { getStreamUrl } from "../services/api";
import { Maximize2, Minimize2, VideoOff, Activity, ShieldCheck, Flame } from "lucide-react";

interface LiveGridProps {
  cameras: Camera[];
  selectedCameraId: string | null;
  onSelectCamera: (id: string) => void;
  onEditRules: (camera: Camera) => void;
}

export const LiveGrid: React.FC<LiveGridProps> = ({
  cameras,
  selectedCameraId,
  onSelectCamera,
  onEditRules
}) => {
  const [gridLayout, setGridLayout] = useState<"1x1" | "2x2" | "auto">("auto");
  const [fullscreenCamId, setFullscreenCamId] = useState<string | null>(null);

  const displayCameras = fullscreenCamId
    ? cameras.filter((c) => c.id === fullscreenCamId)
    : cameras;

  const getGridClasses = () => {
    if (fullscreenCamId || gridLayout === "1x1") return "grid-cols-1 grid-rows-1";
    if (gridLayout === "2x2") return "grid-cols-2 grid-rows-2";
    if (cameras.length <= 1) return "grid-cols-1";
    if (cameras.length <= 4) return "grid-cols-2";
    return "grid-cols-3";
  };

  return (
    <div className="flex-1 flex flex-col bg-vms-darkest overflow-hidden">
      {/* Barra de Controles del Grid */}
      <div className="h-10 bg-vms-panel/90 border-b border-vms-border px-4 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-2 text-vms-muted font-mono">
          <span>MATRIZ DE MONITOREO:</span>
          <span className="text-white font-bold">{cameras.length} CANALES ACTIVOS</span>
        </div>

        <div className="flex items-center space-x-2">
          <div className="flex items-center bg-vms-darkest rounded border border-vms-border p-0.5 font-mono">
            <button
              onClick={() => {
                setFullscreenCamId(null);
                setGridLayout("auto");
              }}
              className={`px-2 py-0.5 rounded transition-colors ${
                gridLayout === "auto" && !fullscreenCamId
                  ? "bg-vms-border text-vms-accent"
                  : "text-vms-muted hover:text-white"
              }`}
            >
              AUTO
            </button>
            <button
              onClick={() => {
                setFullscreenCamId(null);
                setGridLayout("1x1");
              }}
              className={`px-2 py-0.5 rounded transition-colors ${
                gridLayout === "1x1" ? "bg-vms-border text-vms-accent" : "text-vms-muted hover:text-white"
              }`}
            >
              1x1
            </button>
            <button
              onClick={() => {
                setFullscreenCamId(null);
                setGridLayout("2x2");
              }}
              className={`px-2 py-0.5 rounded transition-colors ${
                gridLayout === "2x2" ? "bg-vms-border text-vms-accent" : "text-vms-muted hover:text-white"
              }`}
            >
              2x2
            </button>
          </div>
        </div>
      </div>

      {/* Grid de Streams MJPEG */}
      <div className={`flex-1 p-2 grid gap-2 overflow-auto ${getGridClasses()}`}>
        {displayCameras.map((camera) => {
          const streamUrl = getStreamUrl(camera.id);
          const isSelected = selectedCameraId === camera.id;
          const fps = camera.telemetry?.fps ?? 15.0;
          const isStandby = camera.telemetry?.is_standby ?? false;

          return (
            <div
              key={camera.id}
              onClick={() => onSelectCamera(camera.id)}
              className={`relative bg-black rounded border flex flex-col overflow-hidden group transition-all ${
                isSelected
                  ? "border-vms-accent shadow-[0_0_12px_rgba(0,240,255,0.3)] ring-1 ring-vms-accent"
                  : "border-vms-border hover:border-vms-muted"
              }`}
            >
              {/* Barra de Título del Mosaico */}
              <div className="absolute top-0 left-0 right-0 h-8 bg-gradient-to-b from-black/80 via-black/40 to-transparent z-10 px-3 flex items-center justify-between text-xs select-none">
                <div className="flex items-center space-x-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isStandby ? "bg-vms-muted" : "bg-vms-success animate-pulse"
                    }`}
                  />
                  <span className="font-semibold text-white drop-shadow">
                    {camera.name}
                  </span>
                  <span className="font-mono text-[10px] text-vms-accent bg-black/50 px-1 rounded">
                    {fps.toFixed(1)} FPS
                  </span>
                </div>

                <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onEditRules(camera);
                    }}
                    className="p-1 rounded bg-black/60 hover:bg-vms-hover text-white text-[10px] px-1.5 border border-white/20"
                    title="Editar Reglas y Analítica de esta cámara"
                  >
                    Reglas
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFullscreenCamId(fullscreenCamId === camera.id ? null : camera.id);
                    }}
                    className="p-1 rounded bg-black/60 hover:bg-vms-hover text-white border border-white/20"
                    title="Pantalla Completa"
                  >
                    {fullscreenCamId === camera.id ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                  </button>
                </div>
              </div>

              {/* Contenedor del Stream de Vídeo MJPEG */}
              <div className="flex-1 w-full h-full flex items-center justify-center bg-zinc-950 relative">
                {/* Elemento <img> consumiendo el endpoint FastAPI multipart/x-mixed-replace */}
                <img
                  src={streamUrl}
                  alt={camera.name}
                  className="w-full h-full object-contain pointer-events-none"
                  onError={(e) => {
                    // Fallback visual si el stream no está disponible
                    (e.target as HTMLElement).style.display = "none";
                  }}
                />

                {/* Badge OSD de Estado en la esquina inferior */}
                <div className="absolute bottom-2 left-2 z-10 flex items-center space-x-2 bg-black/70 backdrop-blur-sm px-2 py-0.5 rounded border border-white/10 font-mono text-[10px]">
                  <span className="text-vms-muted">ESTADO:</span>
                  <span className={isStandby ? "text-vms-muted" : "text-vms-success font-bold"}>
                    {isStandby ? "STANDBY (MOG2)" : "ACTIVO (iGPU)"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
