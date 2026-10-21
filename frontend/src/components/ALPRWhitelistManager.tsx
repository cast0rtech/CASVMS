import React, { useState, useEffect } from 'react';
import { ShieldCheck, Car, Trash2, Plus, AlertCircle } from 'lucide-react';

interface WhitelistRecord {
  plate: string;
  owner: string;
  added_at?: string;
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';

export default function ALPRWhitelistManager() {
  const [records, setRecords] = useState<WhitelistRecord[]>([]);
  const [newPlate, setNewPlate] = useState('');
  const [newOwner, setNewOwner] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Cargar lista blanca al montar el componente
  useEffect(() => {
    fetchWhitelist();
  }, []);

  const fetchWhitelist = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/alpr/whitelist`);
      if (!response.ok) throw new Error('Error de conexión con el VMS');
      const data = await response.json();
      
      if (Array.isArray(data)) {
        setRecords(data.map((r: any) => ({
          plate: r.plate || r.plate_number,
          owner: r.owner || r.owner_name,
          added_at: r.added_at || r.created_at
        })));
      } else if (data && Array.isArray(data.records)) {
        setRecords(data.records);
      } else {
        setRecords([]);
      }
      setError(null);
    } catch (err) {
      setError('No se pudo cargar la base de datos de accesos.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddRecord = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPlate.trim() || !newOwner.trim()) return;

    // Normalizar antes de enviar (por seguridad extra, aunque el backend también lo hace)
    const cleanPlate = newPlate.toUpperCase().replace(/\s+/g, '');

    try {
      const response = await fetch(`${API_BASE}/api/alpr/whitelist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate: cleanPlate, owner: newOwner.trim() })
      });

      if (response.ok) {
        // Actualización optimista del estado UI
        setRecords(prev => {
          const filtered = prev.filter(r => r.plate !== cleanPlate);
          return [{ plate: cleanPlate, owner: newOwner.trim(), added_at: 'Ahora' }, ...filtered];
        });
        setNewPlate('');
        setNewOwner('');
      }
    } catch (err) {
      console.error('Error al registrar matrícula:', err);
    }
  };

  const handleDeleteRecord = async (plate: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/alpr/whitelist/${encodeURIComponent(plate)}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setRecords(prev => prev.filter(r => r.plate !== plate));
      }
    } catch (err) {
      console.error('Error al eliminar matrícula:', err);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-950 border border-gray-700 rounded-lg overflow-hidden font-sans max-w-4xl mx-auto mt-6">
      {/* Cabecera */}
      <div className="p-4 border-b border-gray-800 bg-gray-900 flex items-center justify-between">
        <h2 className="text-white font-semibold flex items-center gap-2">
          <ShieldCheck size={20} className="text-blue-500" />
          Control de Accesos (ALPR Whitelist)
        </h2>
        <span className="text-xs font-mono text-gray-400 bg-gray-800 px-2 py-1 rounded border border-gray-700">
          Total: {records.length} vehículos
        </span>
      </div>

      <div className="flex flex-col md:flex-row flex-1 p-4 gap-6">
        {/* Formulario de Ingreso (Izquierda) */}
        <div className="w-full md:w-1/3">
          <form onSubmit={handleAddRecord} className="bg-gray-900 p-4 rounded border border-gray-800 flex flex-col gap-4">
            <h3 className="text-sm font-medium text-gray-300 border-b border-gray-700 pb-2">Registrar Vehículo</h3>
            
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-mono">MATRÍCULA</label>
              <div className="relative">
                <Car size={16} className="absolute left-3 top-3 text-gray-500" />
                <input
                  type="text"
                  required
                  placeholder="ZH 123456"
                  className="w-full bg-black border border-gray-700 text-white rounded py-2 pl-9 pr-3 uppercase font-mono text-sm focus:border-blue-500 focus:outline-none transition-colors"
                  value={newPlate}
                  onChange={(e) => setNewPlate(e.target.value.toUpperCase())}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-mono">PROPIETARIO / DEPARTAMENTO</label>
              <input
                type="text"
                required
                placeholder="Ej. Juan Pérez - Mantenimiento"
                className="w-full bg-black border border-gray-700 text-white rounded py-2 px-3 text-sm focus:border-blue-500 focus:outline-none transition-colors"
                value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
              />
            </div>

            <button 
              type="submit"
              disabled={!newPlate || !newOwner}
              className="mt-2 bg-blue-700 hover:bg-blue-600 disabled:bg-gray-800 disabled:text-gray-500 text-white py-2 rounded flex items-center justify-center gap-2 transition-colors text-sm font-medium"
            >
              <Plus size={16} />
              Añadir a Whitelist
            </button>
          </form>
        </div>

        {/* Tabla de Datos (Derecha) */}
        <div className="w-full md:w-2/3 flex flex-col bg-gray-900 border border-gray-800 rounded">
          <div className="grid grid-cols-12 bg-gray-950 border-b border-gray-800 p-3 text-xs font-mono text-gray-400">
            <div className="col-span-4">MATRÍCULA</div>
            <div className="col-span-5">PROPIETARIO</div>
            <div className="col-span-3 text-right">ACCIONES</div>
          </div>
          
          <div className="flex-1 overflow-y-auto max-h-[400px] custom-scrollbar p-2 space-y-1">
            {loading ? (
              <div className="p-4 text-center text-gray-500 text-sm">Cargando base de datos...</div>
            ) : error ? (
              <div className="p-4 text-center text-red-400 flex items-center justify-center gap-2 text-sm">
                <AlertCircle size={16} /> {error}
              </div>
            ) : records.length === 0 ? (
              <div className="p-8 text-center text-gray-500 text-sm flex flex-col items-center">
                <ShieldCheck size={32} className="mb-2 opacity-20" />
                No hay vehículos autorizados.
              </div>
            ) : (
              records.map((record) => (
                <div key={record.plate} className="grid grid-cols-12 bg-gray-950/50 hover:bg-gray-800 items-center p-2 rounded border border-transparent hover:border-gray-700 transition-colors">
                  <div className="col-span-4 font-mono text-blue-400 font-bold text-sm bg-blue-900/10 py-1 px-2 rounded w-fit border border-blue-900/30">
                    {record.plate}
                  </div>
                  <div className="col-span-5 text-gray-200 text-sm truncate pr-2">
                    {record.owner}
                  </div>
                  <div className="col-span-3 flex justify-end">
                    <button
                      onClick={() => handleDeleteRecord(record.plate)}
                      className="text-gray-500 hover:text-red-400 hover:bg-red-900/30 p-2 rounded transition-colors"
                      title="Revocar acceso"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
