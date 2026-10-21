// ==============================================================================
// CASVMS - Affine Transformation & Vector Math Utilities
// ==============================================================================
import { Point2D } from "../types/vms";

export interface AffineMatrix {
  scale: number;
  tx: number;
  ty: number;
}

/**
 * Transforma un punto de coordenadas de pantalla (Mouse Event en Canvas)
 * a coordenadas del mundo (Espacio original de la imagen 1280x720).
 */
export function screenToWorld(
  screenPos: Point2D,
  matrix: AffineMatrix
): Point2D {
  const [sx, sy] = screenPos;
  const wx = (sx - matrix.tx) / matrix.scale;
  const wy = (sy - matrix.ty) / matrix.scale;
  return [wx, wy];
}

/**
 * Transforma un punto de coordenadas del mundo a coordenadas de pantalla.
 */
export function worldToScreen(
  worldPos: Point2D,
  matrix: AffineMatrix
): Point2D {
  const [wx, wy] = worldPos;
  const sx = wx * matrix.scale + matrix.tx;
  const sy = wy * matrix.scale + matrix.ty;
  return [sx, sy];
}

/**
 * Distancia euclidiana entre dos puntos.
 */
export function distanceBetween(p1: Point2D, p2: Point2D): number {
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  return Math.hypot(dx, dy);
}

/**
 * Hit Detection: Distancia perpendicular mínima desde un punto P a un segmento [A, B].
 */
export function distancePointToSegment(p: Point2D, a: Point2D, b: Point2D): number {
  const l2 = Math.pow(b[0] - a[0], 2) + Math.pow(b[1] - a[1], 2);
  if (l2 === 0) return distanceBetween(p, a);

  // Proyección escalar sobre el segmento
  let t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / l2;
  t = Math.max(0, Math.min(1, t));

  const projX = a[0] + t * (b[0] - a[0]);
  const projY = a[1] + t * (b[1] - a[1]);
  return distanceBetween(p, [projX, projY]);
}

/**
 * Restringe el vector a líneas ortogonales (horizontal o vertical)
 * al mantener presionada la tecla Shift.
 */
export function snapOrthogonal(anchor: Point2D, target: Point2D): Point2D {
  const dx = Math.abs(target[0] - anchor[0]);
  const dy = Math.abs(target[1] - anchor[1]);

  if (dx > dy) {
    // Restricción horizontal
    return [target[0], anchor[1]];
  } else {
    // Restricción vertical
    return [anchor[0], target[1]];
  }
}
