import React from "react";
import { AlertEvent, Severity } from "../types/vms";
import {
  Bell,
  AlertTriangle,
  ShieldAlert,
  Info,
  CheckCircle2,
  Trash2,
  Clock
} from "lucide-react";

interface AlertPanelProps {
  alerts: AlertEvent[];
  onClearAlerts: () => void;
  isOpen: boolean;
  onToggle: () => void;
}

export const AlertPanel: React.FC<AlertPanelProps> = ({
  alerts,
  onClearAlerts,
  isOpen,
  onToggle
}) => {
  const getSeverityBadge = (severity: Severity) => {
    switch (severity) {
      case "critical":
      case "high":
        return {
          icon: <ShieldAlert size={14} className="text-vms-alarm animate-bounce" />,
          bg: "bg-red-950/60 border-red-800/80 text-red-200",
          tag: "HIGH ALARM"
        };
      case "warning":
        return {
          icon: <AlertTriangle size={14} className="text-vms-warning" />,
          bg: "bg-amber-950/60 border-amber-800/80 text-amber-200",
          tag: "WARNING"
        };
      case "info":
      default:
        return {
          icon: <Info size={14} className="text-vms-accent" />,
          bg: "bg-cyan-950/40 border-cyan-800/60 text-cyan-200",
          tag: "INFO"
        };
    }
  };

  return (
    <aside
      className={`bg-vms-panel border-l border-vms-border flex flex-col transition-all duration-300 z-20 ${
        isOpen ? "w-80" : "w-10"
      }`}
    >
      {/* Cabecera del Panel de Alertas */}
      <div className="h-10 bg-vms-darkest/80 border-b border-vms-border px-3 flex items-center justify-between text-xs select-none">
        <button
          onClick={onToggle}
          className="flex items-center space-x-2 text-vms-text hover:text-white font-mono"
        >
          <Bell size={14} className={alerts.length > 0 ? "text-vms-alarm animate-pulse" : "text-vms-muted"} />
          {isOpen && (
            <span className="font-bold tracking-wider">
              ALARMAS ({alerts.length})
            </span>
          )}
        </button>

        {isOpen && alerts.length > 0 && (
          <button
            onClick={onClearAlerts}
            title="Limpiar registro de alarmas"
            className="text-vms-muted hover:text-white transition-colors"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>

      {/* Lista Desplegable de Eventos SSE */}
      {isOpen && (
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {alerts.length === 0 ? (
            <div className="h-40 flex flex-col items-center justify-center text-vms-muted text-xs font-mono text-center px-4">
              <CheckCircle2 size={24} className="text-vms-success mb-2 opacity-60" />
              <span>Sin incidentes activos</span>
              <span className="text-[10px] text-vms-muted/70 mt-1">
                Monitoreo perimetral en guardia
              </span>
            </div>
          ) : (
            alerts.map((alert) => {
              const badge = getSeverityBadge(alert.severity);
              const dateStr = new Date(alert.timestamp * 1000).toLocaleTimeString();

              return (
                <div
                  key={alert.alert_id}
                  className={`p-2.5 rounded border text-xs flex flex-col space-y-1.5 transition-all ${badge.bg}`}
                >
                  <div className="flex items-center justify-between font-mono">
                    <div className="flex items-center space-x-1.5">
                      {badge.icon}
                      <span className="font-bold text-[10px] tracking-wide">
                        {badge.tag}
                      </span>
                    </div>
                    <div className="flex items-center space-x-1 text-[10px] opacity-75">
                      <Clock size={10} />
                      <span>{dateStr}</span>
                    </div>
                  </div>

                  <p className="text-[11px] leading-tight text-white font-medium">
                    {alert.message}
                  </p>

                  <div className="flex items-center justify-between text-[10px] opacity-70 font-mono pt-0.5 border-t border-white/10">
                    <span>CAM: {alert.camera_id}</span>
                    <span className="uppercase">{alert.rule_type}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </aside>
  );
};
