import React, { useState, useEffect } from "react";
import {
  Server,
  Camera as CameraIcon,
  Plus,
  Trash2,
  Edit2,
  RefreshCw,
  Search,
  Upload,
  Download,
  CheckCircle,
  AlertTriangle,
  Radio,
  Sliders,
  Play,
  Save,
  Cpu,
  Activity,
  Layers,
  Network
} from "lucide-react";
import { Camera, ModbusConfig, ModbusStatus, ONVIFDevice } from "../types/vms";
import {
  fetchCameras,
  saveCamera,
  deleteCamera,
  importCameras,
  discoverONVIFCameras,
  testCameraStream,
  fetchModbusConfig,
  saveModbusConfig,
  fetchModbusStatus,
  testModbusOutput
} from "../services/api";

interface ConfigurationPanelProps {
  onCamerasUpdated?: (cameras: Camera[]) => void;
}

export const ConfigurationPanel: React.FC<ConfigurationPanelProps> = ({ onCamerasUpdated }) => {
  const [activeSubTab, setActiveSubTab] = useState<"cameras" | "modbus">("cameras");

  // State: Cameras
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isLoadingCameras, setIsLoadingCameras] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Partial<Camera> | null>(null);
  const [isNewCameraModalOpen, setIsNewCameraModalOpen] = useState(false);
  const [testingStreamId, setTestingStreamId] = useState<string | null>(null);
  const [streamTestResult, setStreamTestResult] = useState<Record<string, { success: boolean; text: string }>>({});

  // State: ONVIF Discovery
  const [isDiscoveringONVIF, setIsDiscoveringONVIF] = useState(false);
  const [discoveredDevices, setDiscoveredDevices] = useState<ONVIFDevice[]>([]);
  const [onvifScanDone, setOnvifScanDone] = useState(false);

  // State: Import Modal
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importMode, setImportMode] = useState<"json" | "csv" | "text">("text");
  const [importText, setImportText] = useState("");
  const [replaceAll, setReplaceAll] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);

  // State: Modbus
  const [modbusConfig, setModbusConfig] = useState<ModbusConfig | null>(null);
  const [modbusStatus, setModbusStatus] = useState<ModbusStatus | null>(null);
  const [isLoadingModbus, setIsLoadingModbus] = useState(false);
  const [isSavingModbus, setIsSavingModbus] = useState(false);
  const [modbusSaveMessage, setModbusSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [testOutputStatus, setTestOutputStatus] = useState<Record<string, { loading: boolean; message: string; ok?: boolean }>>({});

  // 1. Cargar Cámaras
  const loadCameras = async () => {
    setIsLoadingCameras(true);
    try {
      const data = await fetchCameras();
      setCameras(data);
      if (onCamerasUpdated) onCamerasUpdated(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingCameras(false);
    }
  };

  // 2. Cargar Modbus Config & Status
  const loadModbusData = async () => {
    setIsLoadingModbus(true);
    try {
      const [cfg, status] = await Promise.all([fetchModbusConfig(), fetchModbusStatus()]);
      if (cfg) setModbusConfig(cfg);
      if (status) setModbusStatus(status);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingModbus(false);
    }
  };

  useEffect(() => {
    loadCameras();
    loadModbusData();
  }, []);

  // Polling de registros Modbus cuando la pestaña activa es Modbus
  useEffect(() => {
    if (activeSubTab !== "modbus") return;
    const interval = setInterval(async () => {
      const status = await fetchModbusStatus();
      if (status) setModbusStatus(status);
    }, 3000);
    return () => clearInterval(interval);
  }, [activeSubTab]);

  // Manejador Guardar Cámara Individual
  const handleSaveCamera = async (cam: Partial<Camera>) => {
    if (!cam.id || !cam.name || !cam.rtsp_url) {
      alert("Por favor complete los campos obligatorios (ID, Nombre, URL RTSP)");
      return;
    }
    const res = await saveCamera(cam);
    if (res.success) {
      setIsNewCameraModalOpen(false);
      setEditingCamera(null);
      await loadCameras();
    } else {
      alert(`Error al guardar cámara: ${res.error || "Desconocido"}`);
    }
  };

  // Manejador Eliminar Cámara
  const handleDeleteCamera = async (id: string) => {
    if (!confirm(`¿Eliminar la cámara "${id}"? Se detendrá su worker de IA y captura.`)) return;
    const ok = await deleteCamera(id);
    if (ok) {
      await loadCameras();
    } else {
      alert("No se pudo eliminar la cámara.");
    }
  };

  // Manejador Test RTSP
  const handleTestStream = async (camId: string, rtspUrl: string) => {
    setTestingStreamId(camId);
    setStreamTestResult((prev) => ({ ...prev, [camId]: { success: false, text: "Conectando..." } }));
    const result = await testCameraStream(rtspUrl);
    setTestingStreamId(null);
    if (result.success) {
      setStreamTestResult((prev) => ({
        ...prev,
        [camId]: {
          success: true,
          text: `Online: ${result.resolution || "OK"} @ ${result.fps || 0} FPS`
        }
      }));
    } else {
      setStreamTestResult((prev) => ({
        ...prev,
        [camId]: {
          success: false,
          text: `Inaccesible: ${result.error || "Timeout de conexión"}`
        }
      }));
    }
  };

  // Manejador ONVIF Discovery
  const handleScanONVIF = async () => {
    setIsDiscoveringONVIF(true);
    setOnvifScanDone(false);
    setDiscoveredDevices([]);
    try {
      const devices = await discoverONVIFCameras();
      setDiscoveredDevices(devices);
      setOnvifScanDone(true);
    } finally {
      setIsDiscoveringONVIF(false);
    }
  };

  // Añadir cámara desde dispositivo ONVIF descubierto
  const handleAddFromONVIF = (dev: ONVIFDevice) => {
    const cleanIp = dev.ip.replace(/[^0-9.]/g, "");
    const generatedId = `cam_onvif_${cleanIp.replace(/\./g, "_")}`;
    const newCam: Partial<Camera> = {
      id: generatedId,
      name: dev.name || `Cámara ONVIF (${cleanIp})`,
      rtsp_url: `rtsp://admin:password@${cleanIp}:554/live/ch0`,
      onvif_ip: cleanIp,
      onvif_port: dev.port || 80,
      enabled: true,
      rules: { tripwires: [], zones: [] }
    };
    setEditingCamera(newCam);
    setIsNewCameraModalOpen(true);
  };

  // Manejador Importar
  const handleProcessImport = async () => {
    setImportStatus("Procesando importación...");
    try {
      let payload: any = { replace_all: replaceAll };
      if (importMode === "csv" || importMode === "text") {
        if (!importText.trim()) {
          setImportStatus("Error: El texto o CSV no puede estar vacío");
          return;
        }
        // Intentar parsear como JSON si empieza con '['
        if (importText.trim().startsWith("[")) {
          payload.cameras = JSON.parse(importText);
        } else {
          payload.csv_text = importText;
        }
      } else if (importMode === "json") {
        payload.cameras = JSON.parse(importText);
      }

      const res = await importCameras(payload);
      if (res.success) {
        setImportStatus(`¡Importación exitosa! ${res.count ?? 0} cámaras configuradas.`);
        setTimeout(() => {
          setIsImportModalOpen(false);
          setImportText("");
          setImportStatus(null);
          loadCameras();
        }, 1200);
      } else {
        setImportStatus(`Error: ${res.error || "Error al importar"}`);
      }
    } catch (err: any) {
      setImportStatus(`Error de sintaxis: ${err.message}`);
    }
  };

  // Exportar a JSON
  const handleExportJSON = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(cameras, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `casvms_cameras_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Exportar a CSV
  const handleExportCSV = () => {
    const headers = "id,name,rtsp_url,enabled,onvif_ip,onvif_port\n";
    const rows = cameras
      .map(
        (c) =>
          `"${c.id}","${c.name}","${c.rtsp_url}",${c.enabled !== false},"${c.onvif_ip || ""}","${c.onvif_port || 80}"`
      )
      .join("\n");
    const dataStr = "data:text/csv;charset=utf-8," + encodeURIComponent(headers + rows);
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `casvms_cameras_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Carga de archivo para el modal de importación
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setImportText(content);
      if (file.name.endsWith(".json")) setImportMode("json");
      else if (file.name.endsWith(".csv")) setImportMode("csv");
    };
    reader.readAsText(file);
  };

  // Guardar Configuración Modbus
  const handleSaveModbus = async () => {
    if (!modbusConfig) return;
    setIsSavingModbus(true);
    setModbusSaveMessage(null);
    try {
      const ok = await saveModbusConfig(modbusConfig);
      if (ok) {
        setModbusSaveMessage({ type: "success", text: "Configuración Modbus guardada y sincronizada con el servicio." });
        await loadModbusData();
      } else {
        setModbusSaveMessage({ type: "error", text: "Error guardando configuración Modbus." });
      }
    } catch (err: any) {
      setModbusSaveMessage({ type: "error", text: err.message });
    } finally {
      setIsSavingModbus(false);
    }
  };

  // Probar Salida / Pulso Modbus
  const handleTestOutput = async (outputKey: string, coilAddress: number, pulseDuration: number) => {
    setTestOutputStatus((prev) => ({
      ...prev,
      [outputKey]: { loading: true, message: "Enviando pulso..." }
    }));

    const res = await testModbusOutput({
      output_key: outputKey,
      coil_address: coilAddress,
      pulse_duration: pulseDuration
    });

    setTestOutputStatus((prev) => ({
      ...prev,
      [outputKey]: {
        loading: false,
        message: res.success ? `Pulso OK: ${res.message}` : `Error: ${res.error || res.message}`,
        ok: res.success
      }
    }));

    // Auto-limpiar estado después de 4s
    setTimeout(() => {
      setTestOutputStatus((prev) => {
        const copy = { ...prev };
        delete copy[outputKey];
        return copy;
      });
    }, 4000);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-vms-darkest text-vms-text overflow-hidden">
      {/* Sub-Header de Pestañas de Configuración */}
      <div className="h-12 bg-vms-panel/90 border-b border-vms-border flex items-center justify-between px-6 z-10">
        <div className="flex items-center space-x-2">
          <Sliders size={18} className="text-vms-accent" />
          <span className="font-bold text-sm tracking-wide text-white uppercase">Panel de Configuración del Sistema</span>
        </div>

        <div className="flex items-center space-x-1 bg-vms-darkest p-1 rounded border border-vms-border">
          <button
            onClick={() => setActiveSubTab("cameras")}
            className={`flex items-center space-x-2 px-3 py-1 rounded text-xs font-semibold transition-all ${
              activeSubTab === "cameras"
                ? "bg-vms-border text-vms-accent shadow"
                : "text-vms-muted hover:text-white"
            }`}
          >
            <CameraIcon size={14} />
            <span>Gestión e Importación de Cámaras</span>
          </button>

          <button
            onClick={() => setActiveSubTab("modbus")}
            className={`flex items-center space-x-2 px-3 py-1 rounded text-xs font-semibold transition-all ${
              activeSubTab === "modbus"
                ? "bg-vms-border text-vms-accent shadow"
                : "text-vms-muted hover:text-white"
            }`}
          >
            <Network size={14} />
            <span>Salidas Modbus TCP & PLC</span>
          </button>
        </div>
      </div>

      {/* Contenido Principal con Scroll */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* ======================================================== */}
        {/* PESTAÑA 1: GESTIÓN E IMPORTACIÓN DE CÁMARAS             */}
        {/* ======================================================== */}
        {activeSubTab === "cameras" && (
          <div className="space-y-6">
            {/* Barra de Acciones de Cámaras */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-vms-panel p-4 rounded-lg border border-vms-border">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                  <CameraIcon size={16} className="text-vms-accent" />
                  <span>Cámaras de Seguridad ({cameras.length})</span>
                </h3>
                <p className="text-xs text-vms-muted">
                  Gestión dinámica de flujos RTSP, asignación de IA YOLOv8 y descubrimiento de dispositivos ONVIF.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => {
                    setEditingCamera({
                      id: `cam_${Date.now().toString().slice(-4)}`,
                      name: "Nueva Cámara",
                      rtsp_url: "rtsp://",
                      enabled: true,
                      onvif_ip: "",
                      onvif_port: 80,
                      rules: { tripwires: [], zones: [] }
                    });
                    setIsNewCameraModalOpen(true);
                  }}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-vms-accent hover:bg-vms-accent/80 text-vms-darkest font-semibold rounded text-xs transition"
                >
                  <Plus size={14} />
                  <span>Añadir Cámara</span>
                </button>

                <button
                  onClick={() => setIsImportModalOpen(true)}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-xs text-white transition"
                >
                  <Upload size={14} className="text-vms-warning" />
                  <span>Importar (CSV/JSON)</span>
                </button>

                <div className="flex items-center space-x-1 bg-vms-card rounded border border-vms-border p-0.5">
                  <button
                    onClick={handleExportJSON}
                    title="Descargar lista en formato JSON"
                    className="flex items-center space-x-1 px-2.5 py-1 text-xs text-vms-muted hover:text-white transition"
                  >
                    <Download size={12} className="text-vms-accent" />
                    <span>JSON</span>
                  </button>
                  <span className="text-vms-border">|</span>
                  <button
                    onClick={handleExportCSV}
                    title="Descargar lista en formato CSV para Excel"
                    className="flex items-center space-x-1 px-2.5 py-1 text-xs text-vms-muted hover:text-white transition"
                  >
                    <Download size={12} className="text-vms-success" />
                    <span>CSV</span>
                  </button>
                </div>

                <button
                  onClick={handleScanONVIF}
                  disabled={isDiscoveringONVIF}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-vms-card hover:bg-vms-hover border border-vms-accent/40 text-vms-accent rounded text-xs transition disabled:opacity-50"
                >
                  <Search size={14} className={isDiscoveringONVIF ? "animate-spin" : ""} />
                  <span>{isDiscoveringONVIF ? "Escaneando Red..." : "Escanear ONVIF"}</span>
                </button>

                <button
                  onClick={loadCameras}
                  disabled={isLoadingCameras}
                  title="Recargar lista"
                  className="p-1.5 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-vms-muted hover:text-white transition"
                >
                  <RefreshCw size={14} className={isLoadingCameras ? "animate-spin" : ""} />
                </button>
              </div>
            </div>

            {/* Banner de Dispositivos ONVIF Descubiertos (si los hay) */}
            {(isDiscoveringONVIF || onvifScanDone) && (
              <div className="bg-vms-panel border border-vms-accent/30 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Radio size={16} className="text-vms-accent animate-pulse" />
                    <span className="text-xs font-bold text-white uppercase tracking-wider">
                      Descubrimiento de Red ONVIF (WS-Discovery Multicast 3702)
                    </span>
                  </div>
                  <span className="text-xs text-vms-muted">
                    {isDiscoveringONVIF
                      ? "Buscando cámaras compatibles en la subred..."
                      : `${discoveredDevices.length} dispositivo(s) encontrado(s)`}
                  </span>
                </div>

                {discoveredDevices.length === 0 && onvifScanDone && (
                  <p className="text-xs text-vms-muted italic">
                    No se detectaron dispositivos ONVIF en la subred local mediante broadcast UDP. Asegúrese de que la cámara tenga WS-Discovery activo.
                  </p>
                )}

                {discoveredDevices.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {discoveredDevices.map((dev, idx) => (
                      <div
                        key={idx}
                        className="bg-vms-darkest/90 border border-vms-border p-3 rounded flex items-center justify-between"
                      >
                        <div>
                          <div className="text-xs font-bold text-white">{dev.name || `Cámara IP (${dev.ip})`}</div>
                          <div className="text-[11px] font-mono text-vms-muted">
                            IP: {dev.ip}:{dev.port} {dev.model ? `| ${dev.model}` : ""}
                          </div>
                        </div>
                        <button
                          onClick={() => handleAddFromONVIF(dev)}
                          className="px-2 py-1 bg-vms-accent hover:bg-vms-accent/80 text-vms-darkest font-semibold rounded text-[11px] transition"
                        >
                          + Agregar
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Tabla / Lista de Cámaras Existentes */}
            <div className="bg-vms-panel border border-vms-border rounded-lg overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-vms-darkest/80 text-vms-muted uppercase font-mono text-[11px] border-b border-vms-border">
                  <tr>
                    <th className="py-3 px-4">Estado</th>
                    <th className="py-3 px-4">ID de Cámara</th>
                    <th className="py-3 px-4">Nombre Descriptivo</th>
                    <th className="py-3 px-4">URL RTSP / Canal</th>
                    <th className="py-3 px-4">Reglas Activas</th>
                    <th className="py-3 px-4 text-center">Test Stream</th>
                    <th className="py-3 px-4 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-vms-border">
                  {cameras.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-vms-muted font-mono">
                        No hay cámaras configuradas en el sistema. Utilice "Añadir Cámara" o "Importar".
                      </td>
                    </tr>
                  )}
                  {cameras.map((cam) => {
                    const testState = streamTestResult[cam.id];
                    const tripwireCount = cam.rules?.tripwires?.length || 0;
                    const zoneCount = cam.rules?.zones?.length || 0;

                    return (
                      <tr key={cam.id} className="hover:bg-vms-hover/40 transition">
                        {/* Estado */}
                        <td className="py-3 px-4">
                          <div className="flex items-center space-x-1.5">
                            <span
                              className={`w-2.5 h-2.5 rounded-full ${
                                cam.is_alive
                                  ? "bg-vms-success animate-pulse"
                                  : "bg-vms-danger"
                              }`}
                            />
                            <span className="font-mono text-[11px]">
                              {cam.is_alive ? (
                                <span className="text-vms-success font-semibold">ONLINE {cam.pid ? `(${cam.pid})` : ""}</span>
                              ) : (
                                <span className="text-vms-danger font-semibold">DETENIDO</span>
                              )}
                            </span>
                          </div>
                        </td>

                        {/* ID */}
                        <td className="py-3 px-4 font-mono font-semibold text-vms-accent">
                          {cam.id}
                        </td>

                        {/* Nombre */}
                        <td className="py-3 px-4 font-medium text-white">
                          {cam.name}
                        </td>

                        {/* RTSP URL */}
                        <td className="py-3 px-4 font-mono text-vms-muted text-[11px] max-w-xs truncate" title={cam.rtsp_url}>
                          {cam.rtsp_url}
                        </td>

                        {/* Reglas */}
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-vms-darkest border border-vms-border font-mono text-[10px]">
                            <Layers size={10} className="text-vms-accent" />
                            <span>{tripwireCount} Líneas, {zoneCount} Zonas</span>
                          </span>
                        </td>

                        {/* Test RTSP Stream */}
                        <td className="py-3 px-4 text-center">
                          <div className="flex flex-col items-center space-y-1">
                            <button
                              onClick={() => handleTestStream(cam.id, cam.rtsp_url)}
                              disabled={testingStreamId === cam.id}
                              className="px-2 py-1 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-[11px] flex items-center space-x-1 transition disabled:opacity-50"
                            >
                              <Play size={10} className={testingStreamId === cam.id ? "animate-spin" : "text-vms-success"} />
                              <span>{testingStreamId === cam.id ? "Comprobando..." : "Test RTSP"}</span>
                            </button>
                            {testState && (
                              <span
                                className={`text-[10px] font-mono ${
                                  testState.success ? "text-vms-success" : "text-vms-danger"
                                }`}
                              >
                                {testState.text}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Acciones */}
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end space-x-2">
                            <button
                              onClick={() => {
                                setEditingCamera(cam);
                                setIsNewCameraModalOpen(true);
                              }}
                              title="Editar configuración de cámara"
                              className="p-1 hover:bg-vms-card rounded text-vms-muted hover:text-white transition"
                            >
                              <Edit2 size={14} />
                            </button>
                            <button
                              onClick={() => handleDeleteCamera(cam.id)}
                              title="Eliminar cámara"
                              className="p-1 hover:bg-vms-danger/20 rounded text-vms-muted hover:text-vms-danger transition"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* PESTAÑA 2: CONFIGURACIÓN SALIDAS MODBUS TCP & PLC       */}
        {/* ======================================================== */}
        {activeSubTab === "modbus" && (
          <div className="space-y-6">
            {/* Header de Estado Modbus */}
            <div className="flex flex-wrap items-center justify-between gap-4 bg-vms-panel p-4 rounded-lg border border-vms-border">
              <div className="flex items-center space-x-3">
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
                    modbusStatus?.server_running
                      ? "bg-vms-success/20 border-vms-success text-vms-success"
                      : "bg-vms-danger/20 border-vms-danger text-vms-danger"
                  }`}
                >
                  <Server size={20} />
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="text-sm font-bold text-white">Servidor & Pasarela Modbus TCP</h3>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                        modbusStatus?.server_running
                          ? "bg-vms-success/20 text-vms-success border border-vms-success/40"
                          : "bg-vms-danger/20 text-vms-danger border border-vms-danger/40"
                      }`}
                    >
                      {modbusStatus?.server_running ? "SERVER ACTIVO (5020)" : "SERVER DETENIDO"}
                    </span>
                  </div>
                  <p className="text-xs text-vms-muted">
                    Integración con autómatas PLC (Siemens LOGO!, S7-1200, Schneider) para pulso de barreras y alarmas perimetrales.
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <button
                  onClick={loadModbusData}
                  disabled={isLoadingModbus}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-xs text-vms-muted hover:text-white transition"
                >
                  <RefreshCw size={14} className={isLoadingModbus ? "animate-spin" : ""} />
                  <span>Refrescar</span>
                </button>

                <button
                  onClick={handleSaveModbus}
                  disabled={isSavingModbus || !modbusConfig}
                  className="flex items-center space-x-1.5 px-4 py-1.5 bg-vms-accent hover:bg-vms-accent/80 text-vms-darkest font-bold rounded text-xs transition disabled:opacity-50"
                >
                  <Save size={14} />
                  <span>{isSavingModbus ? "Guardando..." : "Guardar Modbus"}</span>
                </button>
              </div>
            </div>

            {modbusSaveMessage && (
              <div
                className={`p-3 rounded text-xs flex items-center space-x-2 border ${
                  modbusSaveMessage.type === "success"
                    ? "bg-vms-success/10 border-vms-success/40 text-vms-success"
                    : "bg-vms-danger/10 border-vms-danger/40 text-vms-danger"
                }`}
              >
                {modbusSaveMessage.type === "success" ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
                <span>{modbusSaveMessage.text}</span>
              </div>
            )}

            {modbusConfig && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Bloque 1: Configuración Servidor Local */}
                <div className="bg-vms-panel p-5 rounded-lg border border-vms-border space-y-4">
                  <div className="flex items-center space-x-2 border-b border-vms-border pb-3">
                    <Server size={16} className="text-vms-accent" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                      1. Servidor Modbus TCP Local (Slave / Servidor de Registros)
                    </h4>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Puerto de Escucha</label>
                      <input
                        type="number"
                        value={modbusConfig.server.port}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            server: { ...modbusConfig.server, port: parseInt(e.target.value) || 5020 }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                      />
                    </div>

                    <div>
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Slave ID / Unit ID</label>
                      <input
                        type="number"
                        value={modbusConfig.server.slave_id}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            server: { ...modbusConfig.server, slave_id: parseInt(e.target.value) || 1 }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                      />
                    </div>

                    <div className="col-span-2">
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Límite de Aforo Máximo (Personas/Vehículos)</label>
                      <input
                        type="number"
                        value={modbusConfig.server.capacity_limit}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            server: { ...modbusConfig.server, capacity_limit: parseInt(e.target.value) || 50 }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                      />
                      <span className="text-[10px] text-vms-muted">
                        Si el aforo supera este valor, se activará la bandera en HR 1 y el relé de sobre-aforo.
                      </span>
                    </div>
                  </div>
                </div>

                {/* Bloque 2: Configuración Cliente PLC Externo */}
                <div className="bg-vms-panel p-5 rounded-lg border border-vms-border space-y-4">
                  <div className="flex items-center space-x-2 border-b border-vms-border pb-3">
                    <Cpu size={16} className="text-vms-warning" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                      2. Autómata PLC Externo (Master / Contactos Secos)
                    </h4>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div className="col-span-2">
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Dirección IP del PLC (Siemens / WAGO / Schneider)</label>
                      <input
                        type="text"
                        value={modbusConfig.plc_client.host}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            plc_client: { ...modbusConfig.plc_client, host: e.target.value }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                        placeholder="192.168.1.50"
                      />
                    </div>

                    <div>
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Puerto Modbus PLC</label>
                      <input
                        type="number"
                        value={modbusConfig.plc_client.port}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            plc_client: { ...modbusConfig.plc_client, port: parseInt(e.target.value) || 502 }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                      />
                    </div>

                    <div>
                      <label className="block text-vms-muted mb-1 font-mono text-[11px]">Unidad Esclava (Unit ID)</label>
                      <input
                        type="number"
                        value={modbusConfig.plc_client.slave_unit}
                        onChange={(e) =>
                          setModbusConfig({
                            ...modbusConfig,
                            plc_client: { ...modbusConfig.plc_client, slave_unit: parseInt(e.target.value) || 1 }
                          })
                        }
                        className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-1.5 text-white font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* Bloque 3: Mapeo de Salidas a Bobinas (Coils) y Prueba */}
                <div className="col-span-1 lg:col-span-2 bg-vms-panel p-5 rounded-lg border border-vms-border space-y-4">
                  <div className="flex items-center justify-between border-b border-vms-border pb-3">
                    <div className="flex items-center space-x-2">
                      <Activity size={16} className="text-vms-success" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                        3. Mapeo de Salidas y Relés Físicos (FC 05: Write Single Coil)
                      </h4>
                    </div>
                    <span className="text-[11px] text-vms-muted font-mono">
                      Accionamiento por contacto seco con auto-reset configurable
                    </span>
                  </div>

                  <div className="space-y-3">
                    {Object.entries(modbusConfig.output_mappings).map(([key, mapping]) => {
                      const status = testOutputStatus[key];

                      return (
                        <div
                          key={key}
                          className="bg-vms-darkest/70 border border-vms-border p-3.5 rounded flex flex-col md:flex-row md:items-center justify-between gap-4"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center space-x-2">
                              <span className="font-semibold text-xs text-white">{mapping.name}</span>
                              <span className="font-mono text-[10px] bg-vms-panel px-1.5 py-0.5 rounded text-vms-accent">
                                ID: {key}
                              </span>
                            </div>
                            <p className="text-[11px] text-vms-muted">{mapping.description}</p>
                          </div>

                          <div className="flex flex-wrap items-center gap-3">
                            <div className="flex items-center space-x-1.5">
                              <span className="text-[11px] text-vms-muted font-mono">Bobina/Coil:</span>
                              <input
                                type="number"
                                value={mapping.coil_address}
                                onChange={(e) => {
                                  const val = parseInt(e.target.value) || 0;
                                  setModbusConfig({
                                    ...modbusConfig,
                                    output_mappings: {
                                      ...modbusConfig.output_mappings,
                                      [key]: { ...mapping, coil_address: val }
                                    }
                                  });
                                }}
                                className="w-16 bg-vms-panel border border-vms-border rounded px-2 py-1 text-xs text-white font-mono text-center"
                              />
                            </div>

                            <div className="flex items-center space-x-1.5">
                              <span className="text-[11px] text-vms-muted font-mono">Pulso (s):</span>
                              <input
                                type="number"
                                step="0.5"
                                min="0.5"
                                max="30"
                                value={mapping.pulse_duration}
                                onChange={(e) => {
                                  const val = parseFloat(e.target.value) || 2.0;
                                  setModbusConfig({
                                    ...modbusConfig,
                                    output_mappings: {
                                      ...modbusConfig.output_mappings,
                                      [key]: { ...mapping, pulse_duration: val }
                                    }
                                  });
                                }}
                                className="w-16 bg-vms-panel border border-vms-border rounded px-2 py-1 text-xs text-white font-mono text-center"
                              />
                            </div>

                            <label className="flex items-center space-x-1.5 cursor-pointer text-xs">
                              <input
                                type="checkbox"
                                checked={mapping.enabled}
                                onChange={(e) => {
                                  setModbusConfig({
                                    ...modbusConfig,
                                    output_mappings: {
                                      ...modbusConfig.output_mappings,
                                      [key]: { ...mapping, enabled: e.target.checked }
                                    }
                                  });
                                }}
                                className="rounded bg-vms-panel border-vms-border text-vms-accent"
                              />
                              <span className="text-vms-muted">Activo</span>
                            </label>

                            <button
                              onClick={() => handleTestOutput(key, mapping.coil_address, mapping.pulse_duration)}
                              disabled={status?.loading}
                              className="px-3 py-1 bg-vms-card hover:bg-vms-hover border border-vms-accent/40 text-vms-accent hover:text-white rounded text-xs font-semibold flex items-center space-x-1 transition disabled:opacity-50"
                            >
                              <Play size={11} className={status?.loading ? "animate-spin" : ""} />
                              <span>{status?.loading ? "Enviando..." : "Disparar Test"}</span>
                            </button>
                          </div>

                          {status && (
                            <div
                              className={`w-full text-right text-[11px] font-mono ${
                                status.ok ? "text-vms-success" : "text-vms-danger"
                              }`}
                            >
                              {status.message}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Bloque 4: Monitor en Vivo de Holding Registers (0-11) */}
                <div className="col-span-1 lg:col-span-2 bg-vms-panel p-5 rounded-lg border border-vms-border space-y-4">
                  <div className="flex items-center justify-between border-b border-vms-border pb-3">
                    <div className="flex items-center space-x-2">
                      <Radio size={16} className="text-vms-accent" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                        4. Monitor de Holding Registers (Lectura en Vivo - 40001+)
                      </h4>
                    </div>
                    <span className="text-[11px] text-vms-muted font-mono">Actualización cada 3 segundos</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
                    {modbusStatus?.registers &&
                      Object.entries(modbusStatus.registers).map(([regIndex, val]) => {
                        let label = `Reg ${regIndex}`;
                        if (regIndex === "0") label = "Aforo Actual";
                        else if (regIndex === "1") label = "Sobre-aforo Flag";
                        else if (regIndex === "2") label = "Total IN";
                        else if (regIndex === "3") label = "Total OUT";
                        else if (regIndex === "4") label = "Intrusión Flag";
                        else if (regIndex === "5") label = "Límite Aforo";
                        else if (regIndex === "6") label = "Estado Barrera";
                        else if (regIndex === "7") label = "Estado Alarma";

                        return (
                          <div
                            key={regIndex}
                            className="bg-vms-darkest border border-vms-border p-3 rounded text-center space-y-1"
                          >
                            <span className="text-[10px] text-vms-muted font-mono uppercase block truncate" title={label}>
                              {label}
                            </span>
                            <span className="text-lg font-bold font-mono text-vms-accent block">
                              {val}
                            </span>
                            <span className="text-[9px] text-vms-border font-mono block">
                              Offset {regIndex} (4000{parseInt(regIndex) + 1})
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ======================================================== */}
      {/* MODAL: AÑADIR / EDITAR CÁMARA                           */}
      {/* ======================================================== */}
      {isNewCameraModalOpen && editingCamera && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-vms-panel border border-vms-border w-full max-w-lg rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-6 py-4 border-b border-vms-border bg-vms-darkest/60">
              <h3 className="font-bold text-sm text-white flex items-center space-x-2">
                <CameraIcon size={16} className="text-vms-accent" />
                <span>Configuración de Cámara</span>
              </h3>
              <button
                onClick={() => {
                  setIsNewCameraModalOpen(false);
                  setEditingCamera(null);
                }}
                className="text-vms-muted hover:text-white transition"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs">
              <div>
                <label className="block text-vms-muted mb-1 font-mono text-[11px]">Identificador Único (ID)</label>
                <input
                  type="text"
                  value={editingCamera.id || ""}
                  onChange={(e) => setEditingCamera({ ...editingCamera, id: e.target.value })}
                  className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-2 text-white font-mono"
                  placeholder="ej. cam_acceso_norte"
                />
              </div>

              <div>
                <label className="block text-vms-muted mb-1 font-mono text-[11px]">Nombre Descriptivo</label>
                <input
                  type="text"
                  value={editingCamera.name || ""}
                  onChange={(e) => setEditingCamera({ ...editingCamera, name: e.target.value })}
                  className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-2 text-white"
                  placeholder="ej. Acceso Principal y Barrera"
                />
              </div>

              <div>
                <label className="block text-vms-muted mb-1 font-mono text-[11px]">
                  URL RTSP del Stream de Video (o "demo")
                </label>
                <input
                  type="text"
                  value={editingCamera.rtsp_url || ""}
                  onChange={(e) => setEditingCamera({ ...editingCamera, rtsp_url: e.target.value })}
                  className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-2 text-white font-mono"
                  placeholder="rtsp://usuario:clave@192.168.1.100:554/ch0"
                />
                <span className="text-[10px] text-vms-muted mt-1 block">
                  Consejo: Use "demo" para generar tráfico de prueba sintético o URL RTSP H.264/H.265.
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-vms-muted mb-1 font-mono text-[11px]">IP ONVIF (Opcional)</label>
                  <input
                    type="text"
                    value={editingCamera.onvif_ip || ""}
                    onChange={(e) => setEditingCamera({ ...editingCamera, onvif_ip: e.target.value })}
                    className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-2 text-white font-mono"
                    placeholder="192.168.1.100"
                  />
                </div>
                <div>
                  <label className="block text-vms-muted mb-1 font-mono text-[11px]">Puerto ONVIF</label>
                  <input
                    type="number"
                    value={editingCamera.onvif_port || 80}
                    onChange={(e) => setEditingCamera({ ...editingCamera, onvif_port: parseInt(e.target.value) || 80 })}
                    className="w-full bg-vms-darkest border border-vms-border rounded px-3 py-2 text-white font-mono"
                  />
                </div>
              </div>

              <label className="flex items-center space-x-2 cursor-pointer pt-2">
                <input
                  type="checkbox"
                  checked={editingCamera.enabled !== false}
                  onChange={(e) => setEditingCamera({ ...editingCamera, enabled: e.target.checked })}
                  className="rounded bg-vms-darkest border-vms-border text-vms-accent"
                />
                <span className="text-white font-semibold">Habilitar procesamiento de cámara y motor de IA</span>
              </label>
            </div>

            <div className="flex items-center justify-end space-x-3 px-6 py-4 border-t border-vms-border bg-vms-darkest/60">
              <button
                onClick={() => {
                  setIsNewCameraModalOpen(false);
                  setEditingCamera(null);
                }}
                className="px-4 py-2 bg-vms-card hover:bg-vms-hover text-vms-muted hover:text-white rounded text-xs transition"
              >
                Cancelar
              </button>
              <button
                onClick={() => handleSaveCamera(editingCamera)}
                className="px-5 py-2 bg-vms-accent hover:bg-vms-accent/80 text-vms-darkest font-bold rounded text-xs transition shadow"
              >
                Guardar Cámara
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL: IMPORTAR CÁMARAS (CSV / JSON)                    */}
      {/* ======================================================== */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-vms-panel border border-vms-border w-full max-w-2xl rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-6 py-4 border-b border-vms-border bg-vms-darkest/60">
              <h3 className="font-bold text-sm text-white flex items-center space-x-2">
                <Upload size={16} className="text-vms-warning" />
                <span>Importación Masiva de Cámaras</span>
              </h3>
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportStatus(null);
                }}
                className="text-vms-muted hover:text-white transition"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs">
              <div className="flex items-center space-x-3">
                <label className="text-vms-muted font-mono text-[11px]">Subir archivo desde disco:</label>
                <input
                  type="file"
                  accept=".json,.csv,.txt"
                  onChange={handleFileUpload}
                  className="text-xs text-vms-muted file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-vms-card file:text-vms-accent hover:file:bg-vms-hover"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-vms-muted font-mono text-[11px]">
                    O pegue el contenido CSV o JSON directamente:
                  </label>
                  <span className="text-[10px] text-vms-muted font-mono">
                    Formato CSV: id,name,rtsp_url,enabled,onvif_ip,onvif_port
                  </span>
                </div>
                <textarea
                  value={importText}
                  onChange={(e) => setImportText(e.target.value)}
                  rows={8}
                  className="w-full bg-vms-darkest border border-vms-border rounded p-3 text-white font-mono text-[11px] focus:outline-none focus:border-vms-accent"
                  placeholder={`cam_01,Entrada Principal,rtsp://admin:pass@192.168.1.101:554/live,true,192.168.1.101,80\ncam_02,Perimetro Este,rtsp://admin:pass@192.168.1.102:554/live,true,192.168.1.102,80`}
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={replaceAll}
                    onChange={(e) => setReplaceAll(e.target.checked)}
                    className="rounded bg-vms-darkest border-vms-border text-vms-danger"
                  />
                  <span className="text-vms-warning font-semibold">
                    Reemplazar todas las cámaras existentes (Sobrescribir)
                  </span>
                </label>
              </div>

              {importStatus && (
                <div className="p-3 bg-vms-darkest border border-vms-border rounded font-mono text-[11px] text-white">
                  {importStatus}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end space-x-3 px-6 py-4 border-t border-vms-border bg-vms-darkest/60">
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportStatus(null);
                }}
                className="px-4 py-2 bg-vms-card hover:bg-vms-hover text-vms-muted hover:text-white rounded text-xs transition"
              >
                Cancelar
              </button>
              <button
                onClick={handleProcessImport}
                className="px-5 py-2 bg-vms-warning hover:bg-vms-warning/80 text-vms-darkest font-bold rounded text-xs transition shadow"
              >
                Procesar e Importar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
