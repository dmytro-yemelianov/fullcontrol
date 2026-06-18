# fullcontrol-ts

A minimal **TypeScript authoring binding** for [FullControl](../). It is a *front-end*: you author a
design with the same primitives FullControl exposes in Python, and `toIR()` emits the **serialized
Toolpath IR (schema v2)** — the exact JSON that `fullcontrol.ir.from_dict` (and the Rust/wasm kernel)
consume. This proves FullControl's core claim: **many front-ends, one IR.**

```
design (TypeScript)  ──toIR()──►  Toolpath IR (v2 JSON)  ──►  Python backends · Rust/wasm kernel · p3d
  point / arc / Extruder           docs/ir_spec.md             simulate · gcode · validate · plot
```

The deposition math is a faithful port of `fullcontrol/ir/toolpath.py::resolve` and
`fullcontrol/core/arc.py`, so IR authored here is **interchangeable** with IR resolved in Python (the
Python proof test `tests/unit/test_ts_ir_binding.py` asserts segment-level and metric equivalence).

## Authoring API

```ts
import { Design, point, arc, Extruder, extrusionGeometry } from './src/fullcontrol.ts';

const d = new Design()
  .extrusionGeometry(0.6, 0.2)   // rectangle bead: area = width * height
  .point(50, 50, 0.2)            // travel to start (extruder defaults OFF -> volume 0)
  .extruder(true)                // start extruding
  .point(70, 50, 0.2)            // a line: length = euclidean distance
  .arc({ x: 60, y: 50 }, { x: 50, y: 50, z: 0.2 }, 'ccw')  // native G3 arc
  .extruder(false);

const ir = d.toIR({
  printSpeed: 1000,              // mm/min for extruding moves
  travelSpeed: 8000,            // mm/min for travels
  filamentDiameter: 1.75,       // feedstock diameter (default 1.75)
  provenance: { design: 'demo', params: {} },
  invariants: ['non_negative_extrusion', 'monotonic_layer_z'],
});
// ir is the serialized v2 IR object; JSON.stringify(ir) is loadable by fullcontrol.ir.from_json
```

Builders (also available as free functions and as chainable `Design` methods):

| builder | meaning |
|---|---|
| `extrusionGeometry(width, height)` | rectangle bead; sets the cross-section area `width*height` |
| `point(x, y, z, color?)` | a move to (x,y,z); any axis `null` inherits from the running state |
| `arc(centre, end, direction, segments?)` | native circular/helical arc — `'cw'`/`'ccw'` → G2/G3 |
| `Extruder(on)` | toggle extrusion on/off (off ⇒ travel move, volume 0) |
| `Design` | accumulates steps; `toIR(opts?)` / `toJSON(opts?, indent?)` |

### The deposition math (mirrors `resolve`)

- **line length** = euclidean distance between start and end (axes undefined in either point are ignored).
- **arc length** = `hypot(radius * swept, dz)` — the same helical formula as `core/arc.py::arc_geometry`
  (swept angle from start/centre/end; `0 → tau` for a full revolution). Arcs are tessellated into
  `arc_points` exactly as in Python (final point snapped to the exact end).
- **deposited_volume** = `length * width * height` while extruding; **0** for travels (extruder off).
- **filament_length** = `deposited_volume / (π·(dia/2)²)`, default `dia = 1.75` (the `volume_to_e`
  factor for `units == "mm"`).
- The v2 header carries `units` (the fixed FullControl conventions), `generator = "fullcontrol-ts
  <ver>"`, optional `provenance`, and declared `invariants` (validated against the recognised vocabulary).

`Extruder` and `ExtrusionGeometry` are also emitted as pass-through `step` events (by class name +
field dump), exactly as Python `resolve` keeps them in the stream, so a downstream g-code dialect sees
them in order.

## Build / generate fixtures

Requires Node ≥ 18 and TypeScript (installed as a devDependency).

```bash
npm install          # typescript + @types/node
npm run lint         # tsc --noEmit (type-check only)
npm run build        # tsc -> dist/
npm run fixtures     # tsc + node dist/generate_fixtures.js -> fixtures/*.ir.json
```

The committed fixtures (`fixtures/square.ir.json`, `fixtures/spiral.ir.json`) are the canonical
TS-produced IR that the Python proof test loads. Regenerate them with `npm run fixtures` after changing
the binding.

## Scope (the common FFF case) — and what is out of scope

In scope: single-tool fused-filament with **1.75 mm** feedstock (configurable), a **rectangle** bead
area (`width*height`), straight lines and **native G2/G3 arcs**, and an on/off extruder mapping to
print/travel. This covers the canonical FullControl designs (perimeters, vases).

Out of scope (deliberately, to keep the binding minimal):

- **Retraction nuances** — explicit retract/unretract moves, z-hop, wipe, `StationaryExtrusion`/
  `MaterialEvent`. Volume is purely `length·area` while extruding; negative-volume retraction is not
  emitted (so `non_negative_extrusion` holds trivially).
- **Non-1.75 / non-circular feedstock** — `filamentDiameter` is configurable, but only the circular
  `volume_to_e = 1/(π·(d/2)²)` model is implemented (no `units == "mm3"` direct-volume mode beyond
  setting an effective factor).
- **Non-rectangle bead models** — `stadium` / `circle` / `manual` area models from
  `ExtrusionGeometry` are not ported (rectangle only).
- **Multi-tool / tool changes**, printer start/end **procedures & primer**, temperature/fan/manual-gcode
  steps, and IR **optimisation passes**. The binding emits only the authored design steps — equivalent
  to Python `resolve(..., include_procedures=False)`.

### Resolve-parity caveat (honest scope)

The Python proof test compares the TS square IR against the *same* square authored in Python and
resolved with `include_procedures=False` (user steps only) on the `generic` printer, whose default
speeds (print 1000 / travel 8000 mm/min) match this binding's defaults. Under those matched conditions
the metrics agree to `rel=1e-9` (segment count, extruded volume, filament length, extruding distance,
total time) **and** the per-segment geometry matches. A *full* Python `transform`/`gcode` run additionally
injects the printer primer and start/end procedures (extra travel/segments), which this binding does not
emit — so equivalence is asserted for the **authored toolpath**, not for a full machine program with
procedures. That is the intended boundary: the IR is interchangeable; machine-specific framing is the
back-end's job.
