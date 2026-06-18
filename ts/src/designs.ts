/**
 * Example designs authored with the fullcontrol-ts binding — mirrors of canonical FullControl designs.
 * Each returns a `Design`; `toIR()` on it yields the serialized v2 IR.
 */
import { Design } from './fullcontrol.ts';

/**
 * A single-layer square perimeter — the simplest extruding design. Travels to the corner with the
 * extruder off, then extrudes the four sides of a `size` x `size` square at height z.
 */
export function square(
  size = 20,
  origin: [number, number] = [50, 50],
  z = 0.2,
  width = 0.6,
  height = 0.2,
): Design {
  const [ox, oy] = origin;
  const d = new Design();
  d.extrusionGeometry(width, height);
  // travel to start (extruder defaults off)
  d.point(ox, oy, z);
  d.extruder(true);
  d.point(ox + size, oy, z);
  d.point(ox + size, oy + size, z);
  d.point(ox, oy + size, z);
  d.point(ox, oy, z);
  d.extruder(false);
  return d;
}

/**
 * A vase-mode spiral (a continuous helix) — port of examples/spiral_vase.py geometry.
 * Constant radius, z rises a little every segment; lobes>0 makes a fluted vase. Uses polyline
 * points (the Python example does too: polar_to_point produces points, not native arcs).
 */
export function spiralVase(
  radius = 15,
  height = 30,
  layerHeight = 0.24,
  segmentsPerLayer = 128,
  lobes = 0,
  lobeDepth = 2,
  extrusionWidth = 0.6,
  centre: [number, number] = [50, 50],
  firstLayerGap = 0.8,
): Design {
  const [cx, cy] = centre;
  const eh = layerHeight;
  const turns = height / eh;
  const totalSegments = Math.max(1, Math.trunc(turns * segmentsPerLayer));
  const d = new Design();
  d.extrusionGeometry(extrusionWidth, eh);
  d.extruder(true); // vase is one continuous extruding helix
  for (let i = 0; i <= totalSegments; i++) {
    const frac = i / segmentsPerLayer; // turns completed so far
    const angle = frac * Math.PI * 2;
    const z = frac * eh + firstLayerGap;
    const r = lobes ? radius + lobeDepth * Math.sin(lobes * angle) : radius;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    d.point(x, y, z);
  }
  return d;
}
