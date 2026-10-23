import React, { useRef, useState, useEffect, useCallback } from "react";
import { Camera, TripwireRule, ZoneRule, Point2D, RuleType } from "../types/vms";
import { getStreamUrl } from "../services/api";
import {
  AffineMatrix,
  screenToWorld,
  worldToScreen,
  distanceBetween,
  distancePointToSegment,
  snapOrthogonal
} from "../utils/affine";
import {
  RotateCcw,
  Trash2,
  Save,
  Shield,
  Clock,
  ArrowRight
} from "lucide-react";

interface RuleEditorCanvasProps {
  camera: Camera;
  onSaveRules: (updatedCamera: Camera) => void;
  onClose: () => void;
}

type DrawMode = "idle" | "drawing_tripwire" | "drawing_zone";

export const RuleEditorCanvas: React.FC<RuleEditorCanvasProps> = ({
  camera,
  onSaveRules,
  onClose
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Reglas locales editables
  const [tripwires, setTripwires] = useState<TripwireRule[]>(camera.rules.tripwires || []);
  const [zones, setZones] = useState<ZoneRule[]>(camera.rules.zones || []);

  // Matriz de Transformación Afín (Zoom y Pan)
  const [matrix, setMatrix] = useState<AffineMatrix>({ scale: 1.0, tx: 0, ty: 0 });

  // Modos de Edición
  const [drawMode, setDrawMode] = useState<DrawMode>("idle");
  const [zoneTypeToDraw, setZoneTypeToDraw] = useState<RuleType>("intrusion");

  // Vértices temporales mientras se dibuja
  const [currentPoints, setCurrentPoints] = useState<Point2D[]>([]);
  const [mouseWorldPos, setMouseWorldPos] = useState<Point2D | null>(null);
  const [isShiftPressed, setIsShiftPressed] = useState<boolean>(false);

  // Selección y Drag & Drop de Nodos
  const [selectedItem, setSelectedItem] = useState<{
    type: "tripwire" | "zone";
    ruleId: string;
    vertexIndex?: number;
  } | null>(null);

  const [isDraggingNode, setIsDraggingNode] = useState<boolean>(false);
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Detección de teclas (Shift para ortogonal, Escape para cancelar, Supr/Delete para borrar)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Shift") setIsShiftPressed(true);
      if (e.key === "Escape") {
        setDrawMode("idle");
        setCurrentPoints([]);
        setSelectedItem(null);
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        handleDeleteSelected();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Shift") setIsShiftPressed(false);
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [selectedItem, tripwires, zones]);

  // Borrar regla o nodo seleccionado
  const handleDeleteSelected = () => {
    if (!selectedItem) return;

    if (selectedItem.type === "tripwire") {
      setTripwires((prev) => prev.filter((tw) => tw.rule_id !== selectedItem.ruleId));
      setSelectedItem(null);
    } else if (selectedItem.type === "zone") {
      if (selectedItem.vertexIndex !== undefined) {
        // Borrar vértice si quedan más de 3
        setZones((prev) =>
          prev.map((z) => {
            if (z.rule_id === selectedItem.ruleId && z.polygon.length > 3) {
              const updated = [...z.polygon];
              updated.splice(selectedItem.vertexIndex!, 1);
              return { ...z, polygon: updated };
            }
            return z;
          })
        );
      } else {
        // Borrar zona completa
        setZones((prev) => prev.filter((z) => z.rule_id !== selectedItem.ruleId));
        setSelectedItem(null);
      }
    }
  };

  // Redibujado del Canvas Nativo con Matriz Afín
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Ajustar tamaño del canvas al contenedor
    if (containerRef.current) {
      canvas.width = containerRef.current.clientWidth;
      canvas.height = containerRef.current.clientHeight;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. DIBUJAR ZONAS POLIGONALES
    zones.forEach((z) => {
      if (z.polygon.length < 3) return;
      const isZoneSelected = selectedItem?.ruleId === z.rule_id;

      ctx.beginPath();
      const firstScreen = worldToScreen(z.polygon[0], matrix);
      ctx.moveTo(firstScreen[0], firstScreen[1]);

      for (let i = 1; i < z.polygon.length; i++) {
        const ptScreen = worldToScreen(z.polygon[i], matrix);
        ctx.lineTo(ptScreen[0], ptScreen[1]);
      }
      ctx.closePath();

      // Relleno semitransparente
      const fillColor =
        z.rule_type === "intrusion"
          ? isZoneSelected
            ? "rgba(255, 42, 85, 0.4)"
            : "rgba(255, 42, 85, 0.2)"
          : isZoneSelected
          ? "rgba(255, 183, 3, 0.4)"
          : "rgba(255, 183, 3, 0.2)";

      const strokeColor =
        z.rule_type === "intrusion" ? "#ff2a55" : "#ffb703";

      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = isZoneSelected ? 3 : 2;
      ctx.stroke();

      // Vértices / Nodos de la Zona con Hit Targets
      z.polygon.forEach((pt, vIdx) => {
        const [vx, vy] = worldToScreen(pt, matrix);
        const isVertexSelected =
          isZoneSelected && selectedItem?.vertexIndex === vIdx;

        ctx.beginPath();
        ctx.arc(vx, vy, isVertexSelected ? 7 : 5, 0, 2 * Math.PI);
        ctx.fillStyle = isVertexSelected ? "#ffffff" : strokeColor;
        ctx.fill();
        ctx.strokeStyle = "#000000";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      // Etiqueta de la regla
      const labelScreen = worldToScreen(z.polygon[0], matrix);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 11px JetBrains Mono, monospace";
      ctx.fillText(`[ZONA] ${z.name}`, labelScreen[0] + 5, labelScreen[1] - 8);
    });

    // 2. DIBUJAR TRIPWIRES DIRECCIONALES
    tripwires.forEach((tw) => {
      const isTwSelected = selectedItem?.ruleId === tw.rule_id;
      const [p1x, p1y] = worldToScreen(tw.pt1, matrix);
      const [p2x, p2y] = worldToScreen(tw.pt2, matrix);

      ctx.beginPath();
      ctx.moveTo(p1x, p1y);
      ctx.lineTo(p2x, p2y);
      ctx.strokeStyle = isTwSelected ? "#ffffff" : "#00f0ff";
      ctx.lineWidth = isTwSelected ? 3.5 : 2.5;
      ctx.stroke();

      // Flecha direccional
      const angle = Math.atan2(p2y - p1y, p2x - p1x);
      const arrowLength = 12;
      ctx.beginPath();
      ctx.moveTo(p2x, p2y);
      ctx.lineTo(
        p2x - arrowLength * Math.cos(angle - Math.PI / 6),
        p2y - arrowLength * Math.sin(angle - Math.PI / 6)
      );
      ctx.moveTo(p2x, p2y);
      ctx.lineTo(
        p2x - arrowLength * Math.cos(angle + Math.PI / 6),
        p2y - arrowLength * Math.sin(angle + Math.PI / 6)
      );
      ctx.strokeStyle = isTwSelected ? "#ffffff" : "#00f0ff";
      ctx.stroke();

      // Nodos A y B
      [tw.pt1, tw.pt2].forEach((pt, nodeIdx) => {
        const [nx, ny] = worldToScreen(pt, matrix);
        const isNodeSelected =
          isTwSelected && selectedItem?.vertexIndex === nodeIdx;

        ctx.beginPath();
        ctx.arc(nx, ny, isNodeSelected ? 6 : 4, 0, 2 * Math.PI);
        ctx.fillStyle = isNodeSelected ? "#ffffff" : "#00f0ff";
        ctx.fill();
        ctx.strokeStyle = "#000";
        ctx.stroke();
      });

      // Etiqueta
      ctx.fillStyle = "#00f0ff";
      ctx.font = "bold 11px JetBrains Mono, monospace";
      ctx.fillText(`[TW] ${tw.name}`, (p1x + p2x) / 2 + 5, (p1y + p2y) / 2 - 8);
    });

    // 3. DIBUJAR TRAZADO EN CURSO
    if (currentPoints.length > 0 && mouseWorldPos) {
      let nextPt = mouseWorldPos;
      if (isShiftPressed && currentPoints.length > 0) {
        nextPt = snapOrthogonal(currentPoints[currentPoints.length - 1], mouseWorldPos);
      }

      ctx.beginPath();
      const first = worldToScreen(currentPoints[0], matrix);
      ctx.moveTo(first[0], first[1]);

      for (let i = 1; i < currentPoints.length; i++) {
        const s = worldToScreen(currentPoints[i], matrix);
        ctx.lineTo(s[0], s[1]);
      }

      const currentTargetScreen = worldToScreen(nextPt, matrix);
      ctx.lineTo(currentTargetScreen[0], currentTargetScreen[1]);

      ctx.strokeStyle = "#06d6a0";
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Dibujar nodos temporales
      currentPoints.forEach((pt) => {
        const [cx, cy] = worldToScreen(pt, matrix);
        ctx.beginPath();
        ctx.arc(cx, cy, 4, 0, 2 * Math.PI);
        ctx.fillStyle = "#06d6a0";
        ctx.fill();
      });
    }
  }, [zones, tripwires, matrix, selectedItem, currentPoints, mouseWorldPos, isShiftPressed]);

  useEffect(() => {
    renderCanvas();
  }, [renderCanvas]);

  // Manejo de Zoom con Rueda del Ratón
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    const newScale = Math.min(Math.max(0.5, matrix.scale * zoomFactor), 4.0);

    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Zoom centrado en el cursor del ratón
    const newTx = mouseX - (mouseX - matrix.tx) * (newScale / matrix.scale);
    const newTy = mouseY - (mouseY - matrix.ty) * (newScale / matrix.scale);

    setMatrix({ scale: newScale, tx: newTx, ty: newTy });
  };

  // Hit Detection para selección o inicio de arrastre de nodos
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || e.altKey) {
      // Paneo con botón central o Alt + Drag
      setIsPanning(true);
      setPanStart({ x: e.clientX - matrix.tx, y: e.clientY - matrix.ty });
      return;
    }

    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const screenPos: Point2D = [e.clientX - rect.left, e.clientY - rect.top];
    const worldPos = screenToWorld(screenPos, matrix);

    if (drawMode === "drawing_tripwire") {
      let finalPos = worldPos;
      if (isShiftPressed && currentPoints.length > 0) {
        finalPos = snapOrthogonal(currentPoints[0], worldPos);
      }

      if (currentPoints.length === 0) {
        setCurrentPoints([finalPos]);
      } else {
        // Segundo punto: crear Tripwire
        const newTw: TripwireRule = {
          rule_id: `tw_${Date.now()}`,
          name: `Línea ${tripwires.length + 1}`,
          pt1: currentPoints[0],
          pt2: finalPos,
          target_classes: ["person", "car"],
          enabled: true
        };
        setTripwires((prev) => [...prev, newTw]);
        setCurrentPoints([]);
        setDrawMode("idle");
      }
      return;
    }

    if (drawMode === "drawing_zone") {
      // Si se hace clic cerca del primer punto y ya hay >= 3 puntos, cerrar polígono
      if (currentPoints.length >= 3) {
        const firstPt = currentPoints[0];
        if (distanceBetween(worldPos, firstPt) < 20 / matrix.scale) {
          const newZone: ZoneRule = {
            rule_id: `zn_${Date.now()}`,
            name: `Zona ${zones.length + 1}`,
            polygon: currentPoints,
            rule_type: zoneTypeToDraw,
            max_dwell_seconds: zoneTypeToDraw === "dwell_time" ? 30 : 0,
            target_classes: ["person", "car"],
            enabled: true
          };
          setZones((prev) => [...prev, newZone]);
          setCurrentPoints([]);
          setDrawMode("idle");
          return;
        }
      }

      let ptToAdd = worldPos;
      if (isShiftPressed && currentPoints.length > 0) {
        ptToAdd = snapOrthogonal(currentPoints[currentPoints.length - 1], worldPos);
      }
      setCurrentPoints((prev) => [...prev, ptToAdd]);
      return;
    }

    // HIT DETECTION EN MODO IDLE:
    // 1. Detectar si se hizo clic en un nodo de zona
    for (const z of zones) {
      for (let i = 0; i < z.polygon.length; i++) {
        const dist = distanceBetween(worldPos, z.polygon[i]);
        if (dist <= 12 / matrix.scale) {
          setSelectedItem({ type: "zone", ruleId: z.rule_id, vertexIndex: i });
          setIsDraggingNode(true);
          return;
        }
      }
    }

    // 2. Detectar si se hizo clic en un nodo de tripwire
    for (const tw of tripwires) {
      if (distanceBetween(worldPos, tw.pt1) <= 12 / matrix.scale) {
        setSelectedItem({ type: "tripwire", ruleId: tw.rule_id, vertexIndex: 0 });
        setIsDraggingNode(true);
        return;
      }
      if (distanceBetween(worldPos, tw.pt2) <= 12 / matrix.scale) {
        setSelectedItem({ type: "tripwire", ruleId: tw.rule_id, vertexIndex: 1 });
        setIsDraggingNode(true);
        return;
      }
    }

    // 3. Detectar si se hizo clic en el segmento de un tripwire
    for (const tw of tripwires) {
      const segDist = distancePointToSegment(worldPos, tw.pt1, tw.pt2);
      if (segDist <= 8 / matrix.scale) {
        setSelectedItem({ type: "tripwire", ruleId: tw.rule_id });
        return;
      }
    }

    // Clic en vacío: deseleccionar
    setSelectedItem(null);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const screenPos: Point2D = [e.clientX - rect.left, e.clientY - rect.top];
    const worldPos = screenToWorld(screenPos, matrix);
    setMouseWorldPos(worldPos);

    if (isPanning) {
      setMatrix((prev) => ({
        ...prev,
        tx: e.clientX - panStart.x,
        ty: e.clientY - panStart.y
      }));
      return;
    }

    if (isDraggingNode && selectedItem && selectedItem.vertexIndex !== undefined) {
      // Arrastrar vértice
      if (selectedItem.type === "zone") {
        setZones((prev) =>
          prev.map((z) => {
            if (z.rule_id === selectedItem.ruleId) {
              const updated = [...z.polygon];
              updated[selectedItem.vertexIndex!] = worldPos;
              return { ...z, polygon: updated };
            }
            return z;
          })
        );
      } else if (selectedItem.type === "tripwire") {
        setTripwires((prev) =>
          prev.map((tw) => {
            if (tw.rule_id === selectedItem.ruleId) {
              return selectedItem.vertexIndex === 0
                ? { ...tw, pt1: worldPos }
                : { ...tw, pt2: worldPos };
            }
            return tw;
          })
        );
      }
    }
  };

  const handleMouseUp = () => {
    setIsDraggingNode(false);
    setIsPanning(false);
  };

  const handleSave = () => {
    const updated: Camera = {
      ...camera,
      rules: {
        tripwires,
        zones
      }
    };
    onSaveRules(updated);
  };

  return (
    <div className="flex-1 flex flex-col bg-vms-darkest relative select-none overflow-hidden">
      {/* Barra de Herramientas Superior del Editor */}
      <div className="h-12 bg-vms-panel border-b border-vms-border px-4 flex items-center justify-between text-xs z-20">
        <div className="flex items-center space-x-3">
          <span className="font-bold text-white uppercase font-mono">
            EDITOR VECTORIAL: {camera.name}
          </span>
          <span className="text-vms-border">|</span>
          <div className="flex items-center space-x-1">
            <button
              onClick={() => {
                setDrawMode("drawing_tripwire");
                setCurrentPoints([]);
              }}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded border text-xs font-mono transition-colors ${
                drawMode === "drawing_tripwire"
                  ? "bg-vms-accent text-black font-bold border-vms-accent"
                  : "bg-vms-card hover:bg-vms-hover text-vms-text border-vms-border"
              }`}
            >
              <ArrowRight size={13} />
              <span>+ Tripwire IN/OUT</span>
            </button>

            <button
              onClick={() => {
                setDrawMode("drawing_zone");
                setZoneTypeToDraw("intrusion");
                setCurrentPoints([]);
              }}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded border text-xs font-mono transition-colors ${
                drawMode === "drawing_zone" && zoneTypeToDraw === "intrusion"
                  ? "bg-vms-alarm text-white font-bold border-vms-alarm"
                  : "bg-vms-card hover:bg-vms-hover text-vms-text border-vms-border"
              }`}
            >
              <Shield size={13} />
              <span>+ Zona Intrusión</span>
            </button>

            <button
              onClick={() => {
                setDrawMode("drawing_zone");
                setZoneTypeToDraw("dwell_time");
                setCurrentPoints([]);
              }}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded border text-xs font-mono transition-colors ${
                drawMode === "drawing_zone" && zoneTypeToDraw === "dwell_time"
                  ? "bg-vms-warning text-black font-bold border-vms-warning"
                  : "bg-vms-card hover:bg-vms-hover text-vms-text border-vms-border"
              }`}
            >
              <Clock size={13} />
              <span>+ Zona Dwell / Parking</span>
            </button>
          </div>
        </div>

        {/* Botones de Acción y Guardado */}
        <div className="flex items-center space-x-2">
          {selectedItem && (
            <button
              onClick={handleDeleteSelected}
              className="flex items-center space-x-1 px-2.5 py-1 bg-red-950 hover:bg-red-900 border border-red-700 text-red-200 rounded text-xs transition-colors"
            >
              <Trash2 size={13} />
              <span>Eliminar Selección</span>
            </button>
          )}

          <button
            onClick={() => setMatrix({ scale: 1.0, tx: 0, ty: 0 })}
            className="p-1 rounded bg-vms-card hover:bg-vms-hover border border-vms-border text-vms-muted hover:text-white"
            title="Resetear Zoom y Posición"
          >
            <RotateCcw size={14} />
          </button>

          <button
            onClick={handleSave}
            className="flex items-center space-x-1.5 px-3 py-1 bg-vms-success hover:bg-emerald-400 text-black font-bold rounded text-xs transition-all shadow-[0_0_12px_rgba(6,214,160,0.3)]"
          >
            <Save size={13} />
            <span>Guardar Reglas</span>
          </button>

          <button
            onClick={onClose}
            className="px-2.5 py-1 bg-vms-card hover:bg-vms-hover border border-vms-border rounded text-xs text-vms-text"
          >
            Cerrar
          </button>
        </div>
      </div>

      {/* Área del Lienzo Interactivo con Transformación Afín */}
      <div
        ref={containerRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        className="flex-1 w-full h-full relative overflow-hidden bg-black cursor-crosshair"
      >
        {/* Stream de Vídeo de Fondo escalado según la Matriz Afín */}
        <img
          src={getStreamUrl(camera.id)}
          alt={camera.name}
          style={{
            transform: `translate(${matrix.tx}px, ${matrix.ty}px) scale(${matrix.scale})`,
            transformOrigin: "0 0"
          }}
          className="absolute top-0 left-0 max-w-none pointer-events-none select-none"
        />

        {/* Capa Vectorial de Canvas Afín */}
        <canvas
          ref={canvasRef}
          className="absolute top-0 left-0 w-full h-full pointer-events-none"
        />

        {/* Guía OSD Inferior */}
        <div className="absolute bottom-3 left-4 bg-black/80 backdrop-blur border border-vms-border rounded px-3 py-1 text-[11px] font-mono text-vms-muted flex items-center space-x-3 pointer-events-none">
          <span>ZOOM: {(matrix.scale * 100).toFixed(0)}%</span>
          <span>|</span>
          <span>PAN: Rueda central / Alt+Drag</span>
          <span>|</span>
          <span className={isShiftPressed ? "text-vms-accent font-bold" : ""}>
            SHIFT: Ortogonal (90°)
          </span>
          {drawMode !== "idle" && (
            <>
              <span>|</span>
              <span className="text-vms-warning font-bold">
                ESC: Cancelar dibujo
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
