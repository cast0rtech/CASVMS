import React from "react";
import {
  Cctv,
  PenTool,
  Film,
  HardDriveDownload,
  UploadCloud,
  RotateCcw,
  Users,
  Car,
  Sliders
} from "lucide-react";
import { SystemTelemetry } from "../types/vms";

interface HeaderProps {
  currentTab: "live" | "rules" | "gallery" | "alpr" | "config";
  onTabChange: (tab: "live" | "rules" | "gallery" | "alpr" | "config") => void;
  telemetry: SystemTelemetry | null;
  onExportConfig: () => void;
  onImportConfig: () => void;
  onResetCounts: () => void;
  activeAlertCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onTabChange,
  telemetry,
  onExportConfig,
  onImportConfig,
  onResetCounts,
  activeAlertCount: _activeAlertCount
}) => {
  const inCount = telemetry?.total_in ?? 0;
  const outCount = telemetry?.total_out ?? 0;
  const occupancy = telemetry?.total_occupancy ?? 0;

  return (
    <header className="h-14 bg-vms-panel border-b border-vms-border flex items-center justify-between px-4 z-30 select-none">
      {/* Logotipo y Título de Estación */}
      <div className="flex items-center space-x-3">
        <div className="w-8 h-8 rounded bg-vms-darkest border border-vms-accent/40 flex items-center justify-center text-vms-accent shadow-[0_0_12px_rgba(0,240,255,0.25)]">
          <Cctv size={18} />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-sm tracking-wider text-white">EDGE-VMS</span>
            <span className="text-[10px] bg-vms-border px-1.5 py-0.5 rounded text-vms-accent font-mono">
              iGPU Edge AI
            </span>
          </div>
          <p className="text-[10px] text-vms-muted font-mono leading-none">
            Zero-Cloud Multiplatform Surveillance Station
          </p>
        </div>
      </div>

      {/* Selector de Modos de Operación */}
      <nav className="flex items-center space-x-1 bg-vms-darkest/70 p-1 rounded border border-vms-border">
        <button
          onClick={() => onTabChange("live")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            currentTab === "live"
              ? "bg-vms-border text-vms-accent shadow-sm"
              : "text-vms-muted hover:text-white hover:bg-vms-hover/50"
          }`}
        >
          <Cctv size={14} />
          <span>Vistas en Vivo</span>
        </button>

        <button
          onClick={() => onTabChange("rules")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            currentTab === "rules"
              ? "bg-vms-border text-vms-accent shadow-sm"
              : "text-vms-muted hover:text-white hover:bg-vms-hover/50"
          }`}
        >
          <PenTool size={14} />
          <span>Editor de Reglas</span>
        </button>

        <button
          onClick={() => onTabChange("gallery")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            currentTab === "gallery"
              ? "bg-vms-border text-vms-accent shadow-sm"
              : "text-vms-muted hover:text-white hover:bg-vms-hover/50"
          }`}
        >
          <Film size={14} />
          <span>Grabaciones (DVR)</span>
        </button>

        <button
          onClick={() => onTabChange("alpr")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            currentTab === "alpr"
              ? "bg-vms-border text-vms-accent shadow-sm"
              : "text-vms-muted hover:text-white hover:bg-vms-hover/50"
          }`}
        >
          <Car size={14} />
          <span>Accesos ALPR</span>
        </button>

        <button
          onClick={() => onTabChange("config")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            currentTab === "config"
              ? "bg-vms-border text-vms-accent shadow-sm"
              : "text-vms-muted hover:text-white hover:bg-vms-hover/50"
          }`}
        >
          <Sliders size={14} />
          <span>Configuración</span>
        </button>
      </nav>


      {/* Indicadores de Aforo y Herramientas SCADA / Backup */}
      <div className="flex items-center space-x-4">
        {/* Telemetría de Aforo Industrial */}
        <div className="flex items-center space-x-3 bg-vms-darkest px-3 py-1 rounded border border-vms-border font-mono text-xs">
          <div className="flex items-center space-x-1.5 text-vms-success">
            <span className="text-[10px] text-vms-muted">IN:</span>
            <span className="font-bold">{inCount}</span>
          </div>
          <span className="text-vms-border">|</span>
          <div className="flex items-center space-x-1.5 text-vms-warning">
            <span className="text-[10px] text-vms-muted">OUT:</span>
            <span className="font-bold">{outCount}</span>
          </div>
          <span className="text-vms-border">|</span>
          <div className="flex items-center space-x-1.5 text-vms-accent">
            <Users size={12} />
            <span className="text-[10px] text-vms-muted">AFORO:</span>
            <span className="font-bold">{occupancy}</span>
          </div>
          <button
            onClick={onResetCounts}
            title="Resetear Aforo Diario (Cron Medianoche)"
            className="text-vms-muted hover:text-white transition-colors ml-1"
          >
            <RotateCcw size={12} />
          </button>
        </div>

        {/* Acciones de Persistencia Nativa Tauri FS & Pendrive */}
        <div className="flex items-center space-x-2">
          <button
            onClick={onExportConfig}
            title="Exportar configuración JSON a Pendrive USB"
            className="flex items-center space-x-1.5 px-2.5 py-1.5 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-xs text-vms-text transition-colors"
          >
            <HardDriveDownload size={13} className="text-vms-accent" />
            <span className="hidden xl:inline">Exportar USB</span>
          </button>

          <button
            onClick={onImportConfig}
            title="Importar configuración JSON desde disco"
            className="flex items-center space-x-1.5 px-2.5 py-1.5 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-xs text-vms-text transition-colors"
          >
            <UploadCloud size={13} className="text-vms-warning" />
            <span className="hidden xl:inline">Importar</span>
          </button>
        </div>
      </div>
    </header>
  );
};
