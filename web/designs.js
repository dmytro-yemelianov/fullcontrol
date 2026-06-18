/**
 * FullControl design catalogue — authored client-side in vanilla JS.
 *
 * Each design is a pure function `(params) -> { events, height, radius }` where `events` is the
 * serialized **Toolpath IR (schema v2)** event list — the exact JSON shape consumed by the Rust/wasm
 * kernel (`simulate_from_ir`, `emit_gcode`) and by `fullcontrol.ir.from_dict` in Python.
 *
 * The deposition math (length / deposited_volume / filament_length) mirrors
 * `fullcontrol/ir/toolpath.py::resolve` and `ts/src/fullcontrol.ts`, so the IR built here is
 * interchangeable with IR resolved by any other FullControl front-end ("many front-ends, one IR").
 *
 * No build step, no bundler: the browser loads this module directly.
 */

// ---- shared printer / authoring constants (the common FFF case) ----
export const EW = 0.8;                       // extrusion width (mm)
export const EH = 0.3;                       // extrusion height / layer height (mm)
export const AREA = EW * EH;                 // rectangle bead cross-section (mm^2)
export const PRINT_SPEED = 1000;             // mm/min
export const TRAVEL_SPEED = 8000;            // mm/min
export const FIL_DIA = 1.75;                 // feedstock diameter (mm)
export const VOL_TO_E = 1 / (Math.PI * (FIL_DIA / 2) ** 2); // mm^3 -> mm of feedstock
export const CX = 100, CY = 100;             // bed centre (mm) — generic 200x200 bed
export const FIRST_GAP = 0.3;                // first-layer z

const TAU = Math.PI * 2;

// ---- IR builders ---------------------------------------------------------

function extrusionGeometryStep(width = EW, height = EH) {
  return { k: 'step', type: 'ExtrusionGeometry',
    data: { area_model: 'rectangle', width, height, diameter: null, area: width * height } };
}
function extruderStep(on) {
  return { k: 'step', type: 'Extruder', data: { on } };
}

/** A straight line segment between two [x,y,z] points (extruding unless travel). */
function lineSeg(s, e, travel, srcIdx, width = EW, height = EH) {
  const len = Math.hypot((e[0] - s[0]) || 0, (e[1] - s[1]) || 0, (e[2] - s[2]) || 0);
  const area = width * height;
  const vol = travel ? 0 : len * area;
  return { k: 'segment', start: s, end: e, travel,
    speed: travel ? TRAVEL_SPEED : PRINT_SPEED, length: len, deposited_volume: vol,
    filament_length: vol * VOL_TO_E, source_index: srcIdx, kind: 'line',
    centre: null, clockwise: false, width, height, color: null, arc_points: null };
}

/**
 * A native circular/helical arc segment from `s` around `centre` to `end`.
 * `clockwise` => G2, else G3. Tessellated into `segs` arc_points for the viewer + length.
 */
function arcSeg(s, centre, end, clockwise, segs, srcIdx, width = EW, height = EH) {
  const [cx, cy] = centre;
  const radius = Math.hypot(s[0] - cx, s[1] - cy);
  const startAngle = Math.atan2(s[1] - cy, s[0] - cx);
  const endAngle = Math.atan2(end[1] - cy, end[0] - cx);
  const mod = (n, m) => ((n % m) + m) % m;
  let swept = clockwise ? mod(startAngle - endAngle, TAU) : mod(endAngle - startAngle, TAU);
  if (swept === 0) swept = TAU;
  const sz = s[2], ez = end[2] != null ? end[2] : sz, dz = ez - sz;
  const arcLength = Math.hypot(radius * swept, dz);
  const sign = clockwise ? -1 : 1;
  const pts = [];
  for (let i = 1; i <= segs; i++) {
    if (i === segs) { pts.push([end[0], end[1], ez]); }
    else {
      const f = i / segs, ang = startAngle + sign * swept * f;
      pts.push([cx + radius * Math.cos(ang), cy + radius * Math.sin(ang), sz + dz * f]);
    }
  }
  const area = width * height, vol = arcLength * area;
  return { k: 'segment', start: s, end: [end[0], end[1], ez], travel: false,
    speed: PRINT_SPEED, length: arcLength, deposited_volume: vol,
    filament_length: vol * VOL_TO_E, source_index: srcIdx, kind: 'arc',
    centre: [cx, cy], clockwise, width, height, color: null, arc_points: pts };
}

/** Wrap a list of [x,y,z] vase points into a continuous extruding spiral (one bead, no travels). */
function spiralFromPoints(pts, width = EW, height = EH) {
  const events = [extrusionGeometryStep(width, height)];
  // travel to first point (extruder off), then extrude the rest
  events.push(lineSeg([null, null, null], pts[0], true, 0, width, height));
  events.push(extruderStep(true));
  for (let i = 1; i < pts.length; i++) {
    events.push(lineSeg(pts[i - 1], pts[i], false, i, width, height));
  }
  return events;
}

// ---- designs -------------------------------------------------------------
// Each: (p) => { events, height, radius }. `height`/`radius` only size the camera + colour ramp.

/** Spiral / fluted vase — the seamless single-wall helix; optional radial lobes flute it. */
function spiralVase(p) {
  const { radius, height, lobes, lobeDepth } = p;
  const segsPerLayer = 128, turns = height / EH;
  const total = Math.max(1, Math.trunc(turns * segsPerLayer));
  const pts = [];
  for (let i = 0; i <= total; i++) {
    const frac = i / segsPerLayer, angle = frac * TAU, z = frac * EH + FIRST_GAP;
    const r = lobes ? radius + lobeDepth * Math.sin(lobes * angle) : radius;
    pts.push([CX + r * Math.cos(angle), CY + r * Math.sin(angle), z]);
  }
  return { events: spiralFromPoints(pts), height, radius: radius + Math.abs(lobeDepth) };
}

/** Twisted / morphing polygon vase — an n-gon cross-section that twists and morphs with height. */
function twistedPolygonVase(p) {
  const { radius, height, sides, morph, twist } = p;
  const segsPerLayer = 128, layerH = EH;
  const total = Math.max(1, Math.trunc((height / layerH) * segsPerLayer));
  const ngonR = (angle, n, R) => {
    const sector = TAU / n, apothem = R * Math.cos(Math.PI / n);
    const a = ((angle % sector) + sector) % sector;
    return apothem / Math.cos(a - sector / 2);
  };
  const pts = [];
  for (let i = 0; i <= total; i++) {
    const ft = i / segsPerLayer, angle = ft * TAU, h = ft * layerH, f = Math.min(1, h / height);
    const tw = f * twist * TAU;
    const rA = ngonR(angle - tw, sides, radius);
    const r = morph === sides ? rA : (1 - f) * rA + f * ngonR(angle - tw, morph, radius);
    pts.push([CX + r * Math.cos(angle), CY + r * Math.sin(angle), h + FIRST_GAP]);
  }
  return { events: spiralFromPoints(pts), height, radius };
}

/**
 * Arc-scalloped vase — built from native fc.Arc (G2/G3) moves. Each layer is a `petals`-petal
 * scalloped cross-section of tangent arcs; helical end-z so it climbs as one spiral. Showcases the
 * native-arc capability: a handful of arc commands per layer, glass-smooth, tiny g-code.
 */
function arcScallopedVase(p) {
  const { radius, height, petals, scallop } = p;
  const layers = Math.max(1, Math.round(height / EH));
  const events = [extrusionGeometryStep()];
  // petal scallop: small circles arranged around the ring; we trace tangent arcs petal-to-petal.
  const ringPoint = (k, z) => {
    const ang = (k / petals) * TAU;
    const r = radius + scallop * Math.cos(petals * ang); // gentle in/out at petal boundaries
    return [CX + r * Math.cos(ang), CY + r * Math.sin(ang), z];
  };
  let srcIdx = 0;
  // travel to first ring point
  const first = ringPoint(0, FIRST_GAP);
  events.push(lineSeg([null, null, null], first, true, srcIdx++, EW, EH));
  events.push(extruderStep(true));
  let cur = first;
  for (let layer = 0; layer < layers; layer++) {
    const zBase = FIRST_GAP + layer * EH;
    for (let k = 1; k <= petals; k++) {
      const z = zBase + (k / petals) * EH;       // helical climb across the layer
      const end = ringPoint(k % petals, z);
      // arc centre: midpoint pulled toward bed centre creates the scallop bulge
      const mx = (cur[0] + end[0]) / 2, my = (cur[1] + end[1]) / 2;
      const dirx = mx - CX, diry = my - CY, dlen = Math.hypot(dirx, diry) || 1;
      const bulge = scallop >= 0 ? 1 : -1;
      const cxp = mx - bulge * (dirx / dlen) * (radius * 0.15);
      const cyp = my - bulge * (diry / dlen) * (radius * 0.15);
      events.push(arcSeg(cur, [cxp, cyp], end, scallop < 0, 16, srcIdx++));
      cur = events[events.length - 1].end;
    }
  }
  return { events, height, radius: radius + Math.abs(scallop) };
}

/**
 * Corrugated snake-mode wall — an OPEN corrugated wall printed snake-mode: print one way, step z up,
 * print back, step up. Sine-wave footprint of `waves` corrugations, lens silhouette (widest at
 * mid-height). A faithful nod to FullControl's Snake-Mode Soapdish. Fat 1mm lines.
 */
function corrugatedWall(p) {
  const { length, height, waves, amplitude } = p;
  const width = 1.0, layerH = EH;
  const layers = Math.max(2, Math.round(height / layerH));
  const pointsPerPass = Math.max(40, waves * 16);
  const events = [extrusionGeometryStep(width, layerH)];
  const x0 = CX - length / 2;
  const lens = (f) => Math.sin(Math.PI * f);   // 0 at ends, 1 at mid-height
  const footprint = (s, amp) => CY + amp * Math.sin(waves * TAU * s);
  // first point + travel
  const f0 = 0, amp0 = amplitude * lens(0 / layers);
  const first = [x0, footprint(0, amp0), FIRST_GAP];
  events.push(lineSeg([null, null, null], first, true, 0, width, layerH));
  events.push(extruderStep(true));
  let srcIdx = 1, cur = first;
  for (let layer = 0; layer < layers; layer++) {
    const z = FIRST_GAP + layer * layerH;
    const amp = amplitude * lens(layer / (layers - 1));
    const reverse = layer % 2 === 1;
    // step up to this layer's z at the current x (a short vertical link keeps it one continuous bead)
    if (layer > 0) { const up = [cur[0], cur[1], z]; events.push(lineSeg(cur, up, false, srcIdx++, width, layerH)); cur = up; }
    for (let i = 1; i <= pointsPerPass; i++) {
      const s = reverse ? 1 - i / pointsPerPass : i / pointsPerPass;
      const x = x0 + s * length, y = footprint(s, amp);
      const np = [x, y, z];
      events.push(lineSeg(cur, np, false, srcIdx++, width, layerH));
      cur = np;
    }
  }
  return { events, height, radius: Math.max(length / 2, amplitude * 2), planar: false };
}

/**
 * Spirograph cup — a hypotrochoid cross-section (a fixed circle R, a rolling circle r, a pen at d)
 * spiralled up into a cup. Classic spirograph rosette walls.
 */
function spirographCup(p) {
  const { R, height, rolling, pen } = p;
  const segsPerLayer = 256, turns = height / EH;
  const total = Math.max(1, Math.trunc(turns * segsPerLayer));
  const r = rolling, d = pen, diff = R - r;
  // scale so the figure roughly fits a ~R radius footprint
  const scale = 1;
  const pts = [];
  for (let i = 0; i <= total; i++) {
    const frac = i / segsPerLayer, t = frac * TAU, z = frac * EH + FIRST_GAP;
    const x = diff * Math.cos(t) + d * Math.cos((diff / r) * t);
    const y = diff * Math.sin(t) - d * Math.sin((diff / r) * t);
    pts.push([CX + x * scale, CY + y * scale, z]);
  }
  return { events: spiralFromPoints(pts), height, radius: (R + d) };
}

/** Fluted / lobed vase — a smooth flute count with a height-driven bulge (ripple-texture flavour). */
function flutedVase(p) {
  const { radius, height, flutes, bulge } = p;
  const segsPerLayer = 160, turns = height / EH;
  const total = Math.max(1, Math.trunc(turns * segsPerLayer));
  const pts = [];
  for (let i = 0; i <= total; i++) {
    const frac = i / segsPerLayer, angle = frac * TAU, h = frac * EH, f = Math.min(1, h / height);
    const belly = 1 + bulge * Math.sin(Math.PI * f);          // wider at the middle
    const flute = 1 + 0.08 * Math.sin(flutes * angle);        // vertical flutes
    const r = radius * belly * flute;
    pts.push([CX + r * Math.cos(angle), CY + r * Math.sin(angle), h + FIRST_GAP]);
  }
  return { events: flutedSpiral(pts), height, radius: radius * (1 + Math.abs(bulge)) };
}
function flutedSpiral(pts) { return spiralFromPoints(pts); }

// ---- catalogue (id -> {name, blurb, technique, build, params}) ----
// params: {key, label, min, max, step, value}

export const DESIGNS = {
  spiral_vase: {
    name: 'Spiral vase',
    technique: 'vase-mode helix',
    blurb: 'The seamless single-wall spiral everything else builds on. Radial lobes flute it.',
    build: spiralVase,
    params: [
      { key: 'radius', label: 'radius (mm)', min: 8, max: 40, step: 1, value: 20 },
      { key: 'height', label: 'height (mm)', min: 10, max: 80, step: 1, value: 40 },
      { key: 'lobes', label: 'lobes', min: 0, max: 12, step: 1, value: 6 },
      { key: 'lobeDepth', label: 'lobe depth (mm)', min: 0, max: 6, step: 0.2, value: 2 },
    ],
  },
  fluted_vase: {
    name: 'Fluted vase',
    technique: 'flutes + height bulge',
    blurb: 'Vertical flutes on a belly that swells toward mid-height — a soft, lobed silhouette.',
    build: flutedVase,
    params: [
      { key: 'radius', label: 'radius (mm)', min: 8, max: 35, step: 1, value: 18 },
      { key: 'height', label: 'height (mm)', min: 10, max: 80, step: 1, value: 45 },
      { key: 'flutes', label: 'flutes', min: 3, max: 24, step: 1, value: 10 },
      { key: 'bulge', label: 'bulge', min: 0, max: 0.8, step: 0.02, value: 0.3 },
    ],
  },
  arc_scalloped_vase: {
    name: 'Arc-scalloped vase (native G2/G3)',
    technique: 'native fc.Arc arcs',
    blurb: 'Each layer is a few tangent native arcs — emits real G2/G3, glass-smooth, tiny g-code.',
    build: arcScallopedVase,
    params: [
      { key: 'radius', label: 'radius (mm)', min: 10, max: 35, step: 1, value: 20 },
      { key: 'height', label: 'height (mm)', min: 10, max: 60, step: 1, value: 30 },
      { key: 'petals', label: 'petals', min: 3, max: 16, step: 1, value: 8 },
      { key: 'scallop', label: 'scallop (mm)', min: -6, max: 6, step: 0.5, value: 3 },
    ],
  },
  twisted_polygon_vase: {
    name: 'Twisted polygon vase',
    technique: 'rotating / morphing n-gon',
    blurb: 'A regular n-gon cross-section that twists with height and morphs to a different vertex count.',
    build: twistedPolygonVase,
    params: [
      { key: 'radius', label: 'radius (mm)', min: 8, max: 30, step: 1, value: 20 },
      { key: 'height', label: 'height (mm)', min: 10, max: 80, step: 1, value: 40 },
      { key: 'sides', label: 'sides', min: 3, max: 10, step: 1, value: 5 },
      { key: 'morph', label: 'morph to sides', min: 3, max: 12, step: 1, value: 8 },
      { key: 'twist', label: 'twist (turns)', min: -2, max: 2, step: 0.05, value: 0.75 },
    ],
  },
  corrugated_wall: {
    name: 'Corrugated snake-mode wall',
    technique: 'open snake-mode wall',
    blurb: 'An open corrugated wall printed snake-mode (up, back, up) — lens silhouette, fat 1mm lines.',
    build: corrugatedWall,
    params: [
      { key: 'length', label: 'length (mm)', min: 30, max: 100, step: 2, value: 60 },
      { key: 'height', label: 'height (mm)', min: 10, max: 60, step: 1, value: 30 },
      { key: 'waves', label: 'corrugations', min: 2, max: 16, step: 1, value: 8 },
      { key: 'amplitude', label: 'amplitude (mm)', min: 1, max: 12, step: 0.5, value: 5 },
    ],
  },
  spirograph_cup: {
    name: 'Spirograph cup',
    technique: 'hypotrochoid spiral',
    blurb: 'A spirograph (hypotrochoid) rosette cross-section spiralled up into a cup wall.',
    build: spirographCup,
    params: [
      { key: 'R', label: 'fixed radius', min: 14, max: 36, step: 1, value: 24 },
      { key: 'height', label: 'height (mm)', min: 10, max: 60, step: 1, value: 35 },
      { key: 'rolling', label: 'rolling radius', min: 3, max: 14, step: 1, value: 7 },
      { key: 'pen', label: 'pen offset', min: 2, max: 14, step: 1, value: 8 },
    ],
  },
};

// ---- helpers for the page -----------------------------------------------

/** Flatten a v2 event list into the polyline [x,y,z...] the viewer draws (arcs expanded). */
export function eventsToPolyline(events) {
  const xyz = [];
  const travelFlags = [];
  let cur = null;
  for (const ev of events) {
    if (ev.k !== 'segment') continue;
    const s = ev.start, e = ev.end;
    const sx = s[0] == null ? (cur ? cur[0] : 0) : s[0];
    const sy = s[1] == null ? (cur ? cur[1] : 0) : s[1];
    const sz = s[2] == null ? (cur ? cur[2] : 0) : s[2];
    if (xyz.length === 0) { xyz.push(sx, sy, sz); travelFlags.push(ev.travel); }
    if (ev.kind === 'arc' && ev.arc_points) {
      let px = sx, py = sy, pz = sz;
      for (const ap of ev.arc_points) {
        const ax = ap[0] == null ? px : ap[0], ay = ap[1] == null ? py : ap[1], az = ap[2] == null ? pz : ap[2];
        xyz.push(ax, ay, az); travelFlags.push(false);
        px = ax; py = ay; pz = az;
      }
      cur = [px, py, pz];
    } else {
      const ex = e[0] == null ? sx : e[0], ey = e[1] == null ? sy : e[1], ez = e[2] == null ? sz : e[2];
      xyz.push(ex, ey, ez); travelFlags.push(ev.travel);
      cur = [ex, ey, ez];
    }
  }
  return { xyz: new Float32Array(xyz), travel: travelFlags };
}

/**
 * Flatten a v2 event list into the list of EXTRUDING segments the realistic (as-printed) renderer
 * meshes. Travels are skipped. Arcs are expanded into their tessellated sub-segments so every entry
 * is a straight bead with explicit start/end and per-segment width/height (mm). Returned in
 * deposition order, so the print-reveal animation can grow them one by one.
 *
 * @returns {Array<{a:[number,number,number], b:[number,number,number], w:number, h:number}>}
 */
export function eventsToSegments(events) {
  const segs = [];
  let cur = null; // running [x,y,z] so segments with null start/end inherit the previous point
  for (const ev of events) {
    if (ev.k !== 'segment') continue;
    const s = ev.start, e = ev.end;
    const sx = s[0] == null ? (cur ? cur[0] : 0) : s[0];
    const sy = s[1] == null ? (cur ? cur[1] : 0) : s[1];
    const sz = s[2] == null ? (cur ? cur[2] : 0) : s[2];
    const w = ev.width != null ? ev.width : EW, h = ev.height != null ? ev.height : EH;
    if (ev.kind === 'arc' && ev.arc_points) {
      let px = sx, py = sy, pz = sz;
      for (const ap of ev.arc_points) {
        const ax = ap[0] == null ? px : ap[0], ay = ap[1] == null ? py : ap[1], az = ap[2] == null ? pz : ap[2];
        if (!ev.travel) segs.push({ a: [px, py, pz], b: [ax, ay, az], w, h });
        px = ax; py = ay; pz = az;
      }
      cur = [px, py, pz];
    } else {
      const ex = e[0] == null ? sx : e[0], ey = e[1] == null ? sy : e[1], ez = e[2] == null ? sz : e[2];
      if (!ev.travel) segs.push({ a: [sx, sy, sz], b: [ex, ey, ez], w, h });
      cur = [ex, ey, ez];
    }
  }
  return segs;
}

/** Build the serialized v2 IR JSON string (header + events) for the wasm kernel. */
export function toIRJSON(events, provenance) {
  return JSON.stringify({
    version: 2,
    units: { length: 'mm', speed: 'mm/min', volume: 'mm^3', flow: 'mm^3/s', temperature: 'degC', angle: 'deg' },
    generator: 'fullcontrol-demo (vanilla JS)',
    provenance: provenance ?? null,
    invariants: ['non_negative_extrusion', 'monotonic_layer_z'],
    events,
  });
}

const START_GCODE = '; FullControl design — full printable g-code, generated in your browser by the Rust (WASM) engine\n'
  + 'G28 ; home all axes\nG90 ; absolute coordinates';
const END_GCODE = 'M104 S0 ; hotend off\nM140 S0 ; bed off\nM107 ; fan off\nG28 X Y ; home x/y\nM84 ; motors off';

/**
 * Wrap a design's event list with the full print procedures (start gcode, heat-up, fan, relative E,
 * end gcode) so `emit_gcode` produces a complete, printable file — like the existing buildFullIR.
 */
export function toFullPrintableIR(events, nozzle, bed) {
  const step = (type, data) => ({ k: 'step', type, data });
  const procedures = [
    step('ManualGcode', { text: START_GCODE }),
    step('Buildplate', { temp: bed, wait: false }), step('Hotend', { temp: nozzle, wait: false }),
    step('Buildplate', { temp: bed, wait: true }), step('Hotend', { temp: nozzle, wait: true }),
    step('Fan', { speed_percent: 100 }),
    step('Extruder', { relative_gcode: true }),
  ];
  const tail = [step('ManualGcode', { text: END_GCODE })];
  return JSON.stringify({ version: 2, events: [...procedures, ...events, ...tail] });
}
