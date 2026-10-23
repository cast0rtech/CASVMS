import React, { useState, useEffect } from "react";
import { RecordingClip } from "../types/vms";
import { fetchRecordings, getRecordingStreamUrl } from "../services/api";
import { exportVideoClipNative } from "../services/tauriStorage";
import {
  Film,
  Download,
  Clock,
  FileVideo,
  Play,
  RefreshCw,
  ShieldAlert
} from "lucide-react";

export const VideoGallery: React.FC = () => {
  const [clips, setClips] = useState<RecordingClip[]>([]);
  const [selectedClip, setSelectedClip] = useState<RecordingClip | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  const loadClips = async () => {
    setIsLoading(true);
    const data = await fetchRecordings();
    setClips(data);
    if (data.length > 0 && !selectedClip) {
      setSelectedClip(data[0]);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    loadClips();
  }, []);

  const handleExportNative = async (clip: RecordingClip) => {
    try {
      setIsExporting(true);
      const success = await exportVideoClipNative(clip.filepath, clip.filename);
      if (success) {
        console.log(`[Tauri] Clip ${clip.filename} exportado exitosamente.`);
      }
    } catch (err) {
      console.error("Error exportando clip:", err);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex-1 flex bg-vms-darkest overflow-hidden">
      {/* Lista Lateral de Grabaciones (Clips MP4 generados por Smart DVR) */}
      <div className="w-96 bg-vms-panel border-r border-vms-border flex flex-col">
        <div className="h-10 bg-vms-darkest/90 border-b border-vms-border px-3 flex items-center justify-between text-xs select-none">
          <div className="flex items-center space-x-2 text-white font-mono font-bold">
            <Film size={14} className="text-vms-accent" />
            <span>GRABACIONES DVR ({clips.length})</span>
          </div>

          <button
            onClick={loadClips}
            disabled={isLoading}
            className="p-1 rounded text-vms-muted hover:text-white hover:bg-vms-hover transition-colors"
            title="Refrescar lista de grabaciones"
          >
            <RefreshCw size={13} className={isLoading ? "animate-spin" : ""} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {clips.length === 0 ? (
            <div className="h-40 flex flex-col items-center justify-center text-vms-muted text-xs font-mono text-center p-4">
              <FileVideo size={32} className="opacity-40 mb-2" />
              <span>No hay clips almacenados</span>
              <span className="text-[10px] opacity-70 mt-1">
                Los clips de 10 min se generan automáticamente ante alarmas
              </span>
            </div>
          ) : (
            clips.map((clip) => {
              const isSelected = selectedClip?.filename === clip.filename;
              const dateStr = new Date(clip.created_at * 1000).toLocaleString();
              const duration = clip.metadata?.duration_seconds ?? 600;

              return (
                <div
                  key={clip.filename}
                  onClick={() => setSelectedClip(clip)}
                  className={`p-2.5 rounded border text-xs cursor-pointer transition-all ${
                    isSelected
                      ? "bg-vms-card border-vms-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]"
                      : "bg-vms-darkest/60 border-vms-border hover:bg-vms-hover/40"
                  }`}
                >
                  <div className="flex items-center justify-between font-mono mb-1">
                    <span className="font-bold text-white truncate max-w-[190px]">
                      {clip.filename}
                    </span>
                    <span className="text-[10px] text-vms-accent bg-vms-border px-1.5 py-0.5 rounded">
                      {clip.size_mb} MB
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-vms-muted font-mono">
                    <div className="flex items-center space-x-1">
                      <Clock size={11} />
                      <span>{duration.toFixed(0)}s</span>
                    </div>
                    <span>{dateStr}</span>
                  </div>

                  {clip.metadata?.rule_name && (
                    <div className="mt-1.5 pt-1 border-t border-vms-border flex items-center space-x-1 text-[10px] text-vms-alarm">
                      <ShieldAlert size={10} />
                      <span>Disparador: {clip.metadata.rule_name}</span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Reproductor de Vídeo HTML5 con Recarga Forzada por Key */}
      <div className="flex-1 flex flex-col bg-black">
        {selectedClip ? (
          <div className="flex-1 flex flex-col h-full">
            {/* Reproductor de Vídeo */}
            <div className="flex-1 relative flex items-center justify-center bg-zinc-950">
              {/* CRÍTICO: Atributo 'key' forzado para garantizar recarga del búfer HTML5 al cambiar de archivo */}
              <video
                key={selectedClip.filename}
                controls
                autoPlay
                className="w-full h-full max-h-[calc(100vh-140px)] object-contain"
              >
                <source
                  src={getRecordingStreamUrl(selectedClip.filename)}
                  type="video/mp4"
                />
                Tu navegador no soporta reproducción directa de vídeo MP4.
              </video>
            </div>

            {/* Barra Inferior de Metadatos y Exportación Nativa */}
            <div className="h-16 bg-vms-panel border-t border-vms-border px-6 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center space-x-6">
                <div>
                  <span className="text-vms-muted block text-[10px]">ARCHIVO ACTIVO</span>
                  <span className="font-bold text-white text-sm">
                    {selectedClip.filename}
                  </span>
                </div>

                <div className="border-l border-vms-border pl-4">
                  <span className="text-vms-muted block text-[10px]">TAMAÑO / DURACIÓN</span>
                  <span className="text-vms-accent">
                    {selectedClip.size_mb} MB | {selectedClip.metadata?.duration_seconds?.toFixed(1) ?? 600}s
                  </span>
                </div>

                <div className="border-l border-vms-border pl-4">
                  <span className="text-vms-muted block text-[10px]">RESOLUCIÓN / FPS</span>
                  <span className="text-white">
                    {selectedClip.metadata?.resolution ?? "1280x720"} @ {selectedClip.metadata?.fps ?? 15} FPS
                  </span>
                </div>
              </div>

              {/* Botón de Exportación Nativa Tauri copyFile hacia Pendrive o Disco */}
              <button
                onClick={() => handleExportNative(selectedClip)}
                disabled={isExporting}
                className="flex items-center space-x-2 px-4 py-2 bg-vms-accent hover:bg-cyan-300 text-black font-bold rounded transition-all shadow-[0_0_12px_rgba(0,240,255,0.3)]"
              >
                <Download size={14} />
                <span>{isExporting ? "Exportando..." : "Exportar a Pendrive (copyFile)"}</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-vms-muted font-mono">
            <Play size={48} className="opacity-30 mb-3" />
            <span>Selecciona un clip del listado para reproducir</span>
          </div>
        )}
      </div>
    </div>
  );
};
