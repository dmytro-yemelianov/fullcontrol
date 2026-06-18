/**
 * fullcontrol-ts — a minimal TypeScript authoring binding for FullControl.
 *
 * It is a *front-end*: you author a design with the same primitives FullControl exposes in Python
 * (points, native arcs, an extruder toggle, an extrusion geometry) and call `toIR()` to emit the
 * **serialized Toolpath IR (schema v2)** — the exact JSON shape `fullcontrol.ir.from_dict` consumes.
 * The deposition math mirrors `fullcontrol/ir/toolpath.py::resolve` and `fullcontrol/core/arc.py`,
 * so the IR produced here is interchangeable with IR resolved in Python ("many front-ends, one IR").
 *
 * Scope: the common FFF case (single 1.75 mm feedstock, rectangle bead area = width*height, lines and
 * native G2/G3 arcs, an on/off extruder => print/travel). See README.md for what is out of scope.
 */

// ---- IR schema constants (must match fullcontrol/ir/serialize.py) ----

export const SCHEMA_VERSION = 2;

/** The fixed FullControl unit conventions (UCUM-style), made explicit in the v2 header. */
export const UNITS = {
  length: 'mm',
  speed: 'mm/min',
  volume: 'mm^3',
  flow: 'mm^3/s',
  temperature: 'degC',
  angle: 'deg',
} as const;

/** Recognised v2 invariant names (must be a subset of INVARIANTS in serialize.py). */
export const INVARIANTS = [
  'non_negative_extrusion',
  'monotonic_layer_z',
  'within_build_volume',
  'no_cold_extrusion',
  'bounded_flow',
] as const;
export type InvariantName = (typeof INVARIANTS)[number];

export const VERSION = '0.1.0';

// ---- Authoring primitives ----

/** A coordinate triple; any axis may be `null` meaning "unchanged / inherited" (as in the IR). */
export type Vec3 = [number | null, number | null, number | null];

export interface Point {
  readonly _kind: 'point';
  x: number | null;
  y: number | null;
  z: number | null;
  color?: [number, number, number] | null;
}

export interface ExtrusionGeometry {
  readonly _kind: 'extrusionGeometry';
  width: number;
  height: number;
}

export interface ExtruderToggle {
  readonly _kind: 'extruder';
  on: boolean;
}

export interface ArcMove {
  readonly _kind: 'arc';
  centre: { x: number; y: number };
  end: { x: number | null; y: number | null; z: number | null };
  clockwise: boolean;
  /** number of straight segments used to tessellate the arc (matches Arc.segments default of 100). */
  segments: number;
}

export type Step = Point | ExtrusionGeometry | ExtruderToggle | ArcMove;

/** A point. Pass `null` for an axis to inherit it from the running state. */
export function point(
  x: number | null,
  y: number | null,
  z: number | null,
  color?: [number, number, number] | null,
): Point {
  return { _kind: 'point', x, y, z, color: color ?? null };
}

/** An extrusion geometry: rectangle bead, area = width * height. */
export function extrusionGeometry(width: number, height: number): ExtrusionGeometry {
  return { _kind: 'extrusionGeometry', width, height };
}

/** Toggle the extruder. `true` => extruding (print speed); `false` => travel (volume 0). */
export function Extruder(on: boolean): ExtruderToggle {
  return { _kind: 'extruder', on };
}

/**
 * A native circular/helical arc move from the current point, around `centre`, to `end`.
 * `direction` is 'clockwise'/'cw' (G2) or 'anticlockwise'/'ccw' (G3) — mirrors core/arc.py.
 */
export function arc(
  centre: { x: number; y: number },
  end: { x: number | null; y: number | null; z: number | null },
  direction: string,
  segments = 100,
): ArcMove {
  return { _kind: 'arc', centre, end, clockwise: isClockwise(direction), segments };
}

const CLOCKWISE = new Set(['clockwise', 'cw']);
const ANTICLOCKWISE = new Set(['anticlockwise', 'anti-clockwise', 'counterclockwise', 'ccw']);

function isClockwise(direction: string): boolean {
  const d = (direction || '').toLowerCase();
  if (CLOCKWISE.has(d)) return true;
  if (ANTICLOCKWISE.has(d)) return false;
  throw new Error(
    `Arc direction must be 'clockwise'/'cw' or 'anticlockwise'/'ccw', got ${JSON.stringify(direction)}`,
  );
}

// ---- Serialized IR event shapes (match serialize.py to_dict output) ----

export interface SegmentEvent {
  k: 'segment';
  start: Vec3;
  end: Vec3;
  travel: boolean;
  speed: number;
  length: number;
  deposited_volume: number;
  filament_length: number;
  source_index: number;
  kind: 'line' | 'arc';
  centre: [number, number] | null;
  clockwise: boolean;
  width: number | null;
  height: number | null;
  color: [number, number, number] | null;
  arc_points: Array<[number | null, number | null, number | null]> | null;
}

export interface StepEvent {
  k: 'step';
  type: string;
  data: Record<string, unknown>;
}

export type IREvent = SegmentEvent | StepEvent;

export interface IRv2 {
  version: 2;
  units: typeof UNITS;
  generator: string;
  provenance: { design?: string; params?: Record<string, unknown> } | null;
  invariants: InvariantName[] | null;
  events: IREvent[];
}

export interface ToIROptions {
  /** print feedrate (mm/min) for extruding moves. */
  printSpeed?: number;
  /** travel feedrate (mm/min) for non-extruding moves. */
  travelSpeed?: number;
  /** feedstock filament diameter (mm). Default 1.75 (the common FFF case). */
  filamentDiameter?: number;
  /** starting extruder state (default off, like a fresh State before the first Extruder(true)). */
  initialExtruderOn?: boolean;
  /** v2 provenance header — what produced this toolpath. */
  provenance?: { design?: string; params?: Record<string, unknown> } | null;
  /** v2 declared invariants (must be from INVARIANTS). */
  invariants?: InvariantName[] | null;
}

// ---- Deposition math (mirror of resolve) ----

function lineLength(s: Vec3, e: Vec3): number {
  const dx = s[0] === null || e[0] === null ? 0 : (e[0] as number) - (s[0] as number);
  const dy = s[1] === null || e[1] === null ? 0 : (e[1] as number) - (s[1] as number);
  const dz = s[2] === null || e[2] === null ? 0 : (e[2] as number) - (s[2] as number);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

const TAU = Math.PI * 2;
const RADIUS_ABS_TOL_MM = 1e-3;
const RADIUS_REL_TOL = 1e-4;

interface ArcGeom {
  cx: number;
  cy: number;
  radius: number;
  startAngle: number;
  swept: number;
  dz: number;
  arcLength: number;
  clockwise: boolean;
}

/** Resolve an arc's geometry from its start position — port of core/arc.py::arc_geometry. */
function arcGeometry(a: ArcMove, sx: number, sy: number, sz: number | null): ArcGeom {
  const { x: cx, y: cy } = a.centre;
  const ex = a.end.x as number;
  const ey = a.end.y as number;
  const radius = Math.hypot(sx - cx, sy - cy);
  const endRadius = Math.hypot(ex - cx, ey - cy);
  if (Math.abs(endRadius - radius) > RADIUS_ABS_TOL_MM + RADIUS_REL_TOL * radius) {
    throw new Error(
      `Arc end point (${ex}, ${ey}) is not on the arc circle ` +
        `(radius from start ${radius.toFixed(4)} != radius from end ${endRadius.toFixed(4)})`,
    );
  }
  const startAngle = Math.atan2(sy - cy, sx - cx);
  const endAngle = Math.atan2(ey - cy, ex - cx);
  const mod = (n: number, m: number) => ((n % m) + m) % m;
  let swept = a.clockwise ? mod(startAngle - endAngle, TAU) : mod(endAngle - startAngle, TAU);
  if (swept === 0) swept = TAU; // coincident start/end -> full revolution
  const dz = a.end.z !== null && sz !== null ? (a.end.z as number) - sz : 0;
  const arcLength = Math.hypot(radius * swept, dz);
  return { cx, cy, radius, startAngle, swept, dz, arcLength, clockwise: a.clockwise };
}

/** Tessellate an arc — port of core/arc.py::arc_points (final point snapped to exact end). */
function arcPoints(a: ArcMove, sz: number | null, g: ArcGeom): Array<[number, number, number | null]> {
  const sign = g.clockwise ? -1 : 1;
  const pts: Array<[number, number, number | null]> = [];
  for (let i = 1; i <= a.segments; i++) {
    if (i === a.segments) {
      pts.push([a.end.x as number, a.end.y as number, a.end.z !== null ? a.end.z : sz]);
    } else {
      const frac = i / a.segments;
      const angle = g.startAngle + sign * g.swept * frac;
      const px = g.cx + g.radius * Math.cos(angle);
      const py = g.cy + g.radius * Math.sin(angle);
      const pz = sz !== null ? sz + g.dz * frac : a.end.z;
      pts.push([px, py, pz]);
    }
  }
  return pts;
}

// ---- Design ----

export class Design {
  private steps: Step[] = [];

  /** Append one or more steps (chainable). */
  add(...steps: Step[]): this {
    this.steps.push(...steps);
    return this;
  }

  point(x: number | null, y: number | null, z: number | null, color?: [number, number, number] | null): this {
    return this.add(point(x, y, z, color));
  }

  extrusionGeometry(width: number, height: number): this {
    return this.add(extrusionGeometry(width, height));
  }

  extruder(on: boolean): this {
    return this.add(Extruder(on));
  }

  arc(
    centre: { x: number; y: number },
    end: { x: number | null; y: number | null; z: number | null },
    direction: string,
    segments = 100,
  ): this {
    return this.add(arc(centre, end, direction, segments));
  }

  /** The accumulated steps (read-only copy). */
  toSteps(): Step[] {
    return [...this.steps];
  }

  /**
   * Resolve the design to the serialized v2 IR — the exact shape `fullcontrol.ir.from_dict` loads.
   * Deposition math mirrors fullcontrol/ir/toolpath.py::resolve.
   */
  toIR(opts: ToIROptions = {}): IRv2 {
    const printSpeed = opts.printSpeed ?? 1000;
    const travelSpeed = opts.travelSpeed ?? 8000;
    const dia = opts.filamentDiameter ?? 1.75;
    const volumeToE = 1 / (Math.PI * (dia / 2) ** 2); // mm^3 -> mm of feedstock

    let on = opts.initialExtruderOn ?? false;
    let width: number | null = null;
    let height: number | null = null;
    let area = 0; // rectangle area = width * height

    // running point (px/py/pz) replicate Point.update_from's None-inheritance, like resolve
    let px: number | null = null;
    let py: number | null = null;
    let pz: number | null = null;

    const events: IREvent[] = [];

    this.steps.forEach((step, i) => {
      if (step._kind === 'arc') {
        if (px === null || py === null) {
          throw new Error('Arc has no start position — a point defining x/y must precede the arc');
        }
        const g = arcGeometry(step, px, py, pz);
        const speed = on ? printSpeed : travelSpeed;
        const vol = on ? g.arcLength * area : 0;
        const start: Vec3 = [px, py, pz];
        const pts = arcPoints(step, pz, g);
        px = step.end.x === null ? px : step.end.x;
        py = step.end.y === null ? py : step.end.y;
        pz = step.end.z === null ? pz : step.end.z;
        const end: Vec3 = [px, py, pz];
        events.push({
          k: 'segment',
          start,
          end,
          travel: !on,
          speed,
          length: g.arcLength,
          deposited_volume: vol,
          filament_length: vol * volumeToE,
          source_index: i,
          kind: 'arc',
          centre: [g.cx, g.cy],
          clockwise: g.clockwise,
          width,
          height,
          color: null,
          arc_points: pts as Array<[number | null, number | null, number | null]>,
        });
      } else if (step._kind === 'point') {
        const start: Vec3 = [px, py, pz];
        px = step.x === null ? px : step.x;
        py = step.y === null ? py : step.y;
        pz = step.z === null ? pz : step.z;
        const end: Vec3 = [px, py, pz];
        if (end[0] !== start[0] || end[1] !== start[1] || end[2] !== start[2]) {
          const length = lineLength(start, end);
          const speed = on ? printSpeed : travelSpeed;
          const vol = on ? length * area : 0;
          events.push({
            k: 'segment',
            start,
            end,
            travel: !on,
            speed,
            length,
            deposited_volume: vol,
            filament_length: vol * volumeToE,
            source_index: i,
            kind: 'line',
            centre: null,
            clockwise: false,
            width,
            height,
            color: step.color ?? null,
            arc_points: null,
          });
        }
      } else if (step._kind === 'extrusionGeometry') {
        width = step.width;
        height = step.height;
        area = step.width * step.height;
        events.push({
          k: 'step',
          type: 'ExtrusionGeometry',
          data: { area_model: 'rectangle', width: step.width, height: step.height, diameter: null, area },
        });
      } else if (step._kind === 'extruder') {
        on = step.on;
        events.push({ k: 'step', type: 'Extruder', data: { on: step.on } });
      }
    });

    const invariants = opts.invariants ?? null;
    if (invariants) {
      const bad = invariants.filter((n) => !(INVARIANTS as readonly string[]).includes(n));
      if (bad.length) throw new Error(`unknown invariant(s) ${JSON.stringify(bad)}`);
    }

    return {
      version: 2,
      units: { ...UNITS },
      generator: `fullcontrol-ts ${VERSION}`,
      provenance: opts.provenance ?? null,
      invariants,
      events,
    };
  }

  /** Convenience: the serialized IR as a JSON string. */
  toJSON(opts: ToIROptions = {}, indent?: number): string {
    return JSON.stringify(this.toIR(opts), null, indent);
  }
}
