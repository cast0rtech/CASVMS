import React, { useState, useEffect } from "react";
import { AuthorizedPlate } from "../types/vms";
import {
  fetchALPRWhitelist,
  addALPRWhitelist,
  deleteALPRWhitelist
} from "../services/api";
import {
  ShieldCheck,
  Plus,
  Trash2,
  Search,
  Car,
  User,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Lock
} from "lucide-react";

export const ALPRAccessPanel: React.FC = () => {
  const [plates, setPlates] = useState<AuthorizedPlate[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Estados del Formulario de Ingreso
  const [newPlate, setNewPlate] = useState<string>("");
  const [newOwner, setNewOwner] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Mensaje de estado / notificación visual
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // 1. Cargar lista al montar el componente (useEffect)
  useEffect(() => {
    loadWhitelist();
  }, []);

  const loadWhitelist = async () => {
    setIsLoading(true);
    try {
      const data = await fetchALPRWhitelist();
      setPlates(data);
    } catch (err) {
      showFeedback("error", "Error conectando con la base de datos de matrículas.");
    } finally {
      setIsLoading(false);
    }
  };

  const showFeedback = (type: "success" | "error", message: string) => {
    setFeedback({ type, message });
    setTimeout(() => setFeedback(null), 4000);
  };

  // 2. Manejo de Envío (POST /api/alpr/whitelist)
  const handleAddPlate = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanPlate = newPlate.trim().toUpperCase();
    const cleanOwner = newOwner.trim();

    if (!cleanPlate || cleanPlate.length < 3) {
      showFeedback("error", "La matrícula debe tener al menos 3 caracteres.");
      return;
    }

    setIsSubmitting(true);
    try {
      const success = await addALPRWhitelist(cleanPlate, cleanOwner);
      if (success) {
        showFeedback("success", `Matrícula [${cleanPlate}] añadida a la whitelist con éxito.`);
        setNewPlate("");
        setNewOwner("");

        // Actualización del estado local sin recargar la página
        const updatedList = await fetchALPRWhitelist();
        setPlates(updatedList);
      } else {
        showFeedback("error", "No se pudo registrar la matrícula en el servidor.");
      }
    } catch (err) {
      showFeedback("error", "Fallo al comunicar con la API de control de acceso.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // 3. Manejo de Eliminación (DELETE /api/alpr/whitelist/{plate})
  const handleDeletePlate = async (plateNumber: string) => {
    if (!confirm(`¿Eliminar la matrícula [${plateNumber}] de la whitelist autorizada?`)) {
      return;
    }

    try {
      const success = await deleteALPRWhitelist(plateNumber);
      if (success) {
        // Actualización optimista del estado local
        setPlates((prev) => prev.filter((p) => p.plate_number !== plateNumber && p.normalized_plate !== plateNumber));
        showFeedback("success", `Matrícula [${plateNumber}] eliminada correctamente.`);
      } else {
        showFeedback("error", "No se pudo eliminar la matrícula del sistema.");
      }
    } catch (err) {
      showFeedback("error", "Error procesando la solicitud de eliminación.");
    }
  };

  // Filtro de búsqueda en tiempo real
  const filteredPlates = plates.filter((p) => {
    const query = searchQuery.toUpperCase();
    return (
      p.plate_number.toUpperCase().includes(query) ||
      p.owner_name.toUpperCase().includes(query)
    );
  });

  return (
    <div className="flex-1 bg-gray-900 text-gray-100 flex flex-col overflow-y-auto p-4 md:p-6 select-none font-sans">
      {/* Cabecera del Panel */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 border-b border-gray-800 gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded bg-cyan-950/70 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.25)]">
              <ShieldCheck size={18} />
            </div>
            <h1 className="text-lg md:text-xl font-bold tracking-wide text-white">
              Gestión de Accesos ALPR (Whitelist)
            </h1>
          </div>
          <p className="text-xs text-gray-400 font-mono mt-1">
            Control de matrículas autorizadas para apertura automática de barrera vía PLC Modbus TCP
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="bg-gray-950/80 px-3 py-1.5 rounded border border-gray-800 flex items-center space-x-2 text-xs font-mono">
            <span className="text-gray-400">VEHÍCULOS AUTORIZADOS:</span>
            <span className="font-bold text-cyan-400 text-sm">{plates.length}</span>
          </div>
          <button
            onClick={loadWhitelist}
            disabled={isLoading}
            className="p-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 transition-colors"
            title="Refrescar base de datos"
          >
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Banner de Feedback / Notificación */}
      {feedback && (
        <div
          className={`mt-4 p-3 rounded border text-xs font-mono flex items-center justify-between transition-all ${
            feedback.type === "success"
              ? "bg-emerald-950/70 border-emerald-700 text-emerald-200"
              : "bg-red-950/70 border-red-700 text-red-200"
          }`}
        >
          <div className="flex items-center space-x-2">
            {feedback.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{feedback.message}</span>
          </div>
          <button
            onClick={() => setFeedback(null)}
            className="opacity-70 hover:opacity-100 text-sm font-bold"
          >
            ×
          </button>
        </div>
      )}

      {/* 1. FORMULARIO DE INGRESO */}
      <div className="mt-6 bg-gray-950/60 p-4 md:p-5 rounded-lg border border-gray-800 shadow-lg">
        <div className="flex items-center space-x-2 text-xs font-mono text-cyan-400 mb-3">
          <Car size={15} />
          <span className="font-bold uppercase tracking-wider">Añadir Vehículo a Lista Blanca</span>
        </div>

        <form onSubmit={handleAddPlate} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          {/* Input Matrícula (Fuerza Mayúsculas Automáticamente) */}
          <div className="md:col-span-4">
            <label className="block text-[11px] font-mono text-gray-400 uppercase mb-1">
              Matrícula / Placa:
            </label>
            <div className="relative">
              <input
                type="text"
                required
                value={newPlate}
                // Fuerzo mayúsculas automáticamente en tiempo real
                onChange={(e) => setNewPlate(e.target.value.toUpperCase())}
                placeholder="Ej. ZURICH-1234"
                className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white font-mono tracking-widest uppercase placeholder-gray-600 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all"
              />
            </div>
          </div>

          {/* Input Nombre del Propietario */}
          <div className="md:col-span-5">
            <label className="block text-[11px] font-mono text-gray-400 uppercase mb-1">
              Propietario / Flota / Conductor:
            </label>
            <div className="relative">
              <input
                type="text"
                value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
                placeholder="Ej. Juan Pérez - Mantenimiento"
                className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all"
              />
            </div>
          </div>

          {/* Botón Añadir a Whitelist */}
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={isSubmitting || !newPlate.trim()}
              className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-800 disabled:text-gray-500 text-black font-bold py-2 px-4 rounded text-xs transition-all flex items-center justify-center space-x-1.5 shadow-[0_0_12px_rgba(6,182,212,0.3)] disabled:shadow-none"
            >
              <Plus size={15} />
              <span>{isSubmitting ? "Registrando..." : "Añadir a Whitelist"}</span>
            </button>
          </div>
        </form>
      </div>

      {/* 2. TABLA DE DATOS DE MATRÍCULAS */}
      <div className="mt-6 flex-1 flex flex-col bg-gray-950/60 rounded-lg border border-gray-800 overflow-hidden shadow-lg">
        {/* Barra de Filtro y Búsqueda */}
        <div className="p-3 bg-gray-950 border-b border-gray-800 flex items-center justify-between text-xs font-mono">
          <div className="flex items-center space-x-2 text-gray-400">
            <Lock size={13} className="text-cyan-400" />
            <span className="font-bold">REGISTROS AUTORIZADOS</span>
          </div>

          <div className="relative w-64 max-w-full">
            <Search size={13} className="absolute left-2.5 top-2.5 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar matrícula o titular..."
              className="w-full bg-gray-900 border border-gray-800 rounded pl-8 pr-3 py-1 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        {/* Tabla Responsiva */}
        <div className="flex-1 overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-gray-900/90 text-gray-400 uppercase font-mono border-b border-gray-800 text-[11px]">
                <th className="py-2.5 px-4 font-semibold">Matrícula (Placa)</th>
                <th className="py-2.5 px-4 font-semibold">Propietario / Área</th>
                <th className="py-2.5 px-4 font-semibold hidden sm:table-cell">Estado Barrera</th>
                <th className="py-2.5 px-4 font-semibold hidden md:table-cell">Fecha de Alta</th>
                <th className="py-2.5 px-4 font-semibold text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/80">
              {filteredPlates.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-10 text-center text-gray-500 font-mono text-xs">
                    {isLoading ? (
                      <div className="flex items-center justify-center space-x-2">
                        <RefreshCw size={14} className="animate-spin text-cyan-400" />
                        <span>Cargando base de datos SQLite...</span>
                      </div>
                    ) : searchQuery ? (
                      `No se encontraron matrículas que coincidan con "${searchQuery}"`
                    ) : (
                      "No hay matrículas autorizadas registradas. Añade una para comenzar."
                    )}
                  </td>
                </tr>
              ) : (
                filteredPlates.map((plate) => (
                  <tr
                    key={plate.id}
                    className="hover:bg-gray-800/40 transition-colors group"
                  >
                    {/* Matrícula con estilo visual de placa vehicular */}
                    <td className="py-3 px-4 font-mono font-bold">
                      <span className="inline-flex items-center bg-gray-950 border border-cyan-500/40 text-cyan-300 px-2.5 py-1 rounded text-xs tracking-wider shadow-sm">
                        <Car size={12} className="mr-1.5 opacity-70" />
                        {plate.plate_number}
                      </span>
                    </td>

                    {/* Propietario */}
                    <td className="py-3 px-4 text-gray-200">
                      <div className="flex items-center space-x-1.5">
                        <User size={13} className="text-gray-500" />
                        <span>{plate.owner_name || "Sin asignar"}</span>
                      </div>
                    </td>

                    {/* Estado de acceso */}
                    <td className="py-3 px-4 hidden sm:table-cell">
                      <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/70 border border-emerald-800 text-emerald-300">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                        <span>AUTORIZADO (PLC ON)</span>
                      </span>
                    </td>

                    {/* Fecha de creación */}
                    <td className="py-3 px-4 font-mono text-gray-400 text-[11px] hidden md:table-cell">
                      {plate.created_at || "Reciente"}
                    </td>

                    {/* Botón de Eliminación (Lucide React Trash2) */}
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDeletePlate(plate.plate_number)}
                        className="p-1.5 rounded bg-red-950/40 hover:bg-red-900/80 text-red-400 hover:text-red-200 border border-red-900/60 transition-colors"
                        title={`Eliminar matrícula ${plate.plate_number}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
