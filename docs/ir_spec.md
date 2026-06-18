# FullControl Toolpath IR — specification

The **Toolpath IR** is FullControl's language-agnostic intermediate representation: the layer between a
*design* (a program that computes geometry) and a *target* (g-code, a plot, a simulation, a validation
report). It is to additive toolpaths roughly what LLVM IR is to programs or glTF is to 3-D assets — a
stable, typed, serialisable contract that many front-ends can emit and many back-ends can consume.

```
design (Python / any language)  ──resolve()──►  Toolpath IR  ──►  backends
   fc.Point / fc.Arc / steps                    (this spec)        gcode · plot · simulate · validate
                                                     │             verify_gcode · optimise_gcode
                                                     ├─ ir/passes.py  (IR→IR optimisation)
                                                     └─ serialize.py  (JSON interchange) ─► Rust kernel · wasm · p3d
```

Why an IR at all, rather than just emitting g-code? G-code is the *target*, not the representation:
it is machine-specific, dialect-fragmented, loses arcs to line segments once a firmware re-tessellates
them, encodes variable bead width only implicitly through per-move extrusion, and carries design intent
only in comments. The IR keeps **motion + per-point process intent** as first-class typed data, so the
same toolpath can be simulated, validated, optimised, reverse-engineered and re-targeted without going
through a lossy g-code round-trip. (See `docs/ir_prior_art.md` for why no existing standard fills this
niche, and which ones to interoperate with.)

## 1. The model

A `Toolpath` is an **ordered stream of events**. Order is significant — it is print order. There are
three event kinds:

| kind | meaning |
|------|---------|
| `segment` | one motion move (a straight line **or** a native arc), carrying its motion + deposition state |
| `material` | deposition with no motion (e.g. `StationaryExtrusion`) — material added in place |
| `step` | any non-motion design step passed through verbatim (temperature, fan, manual g-code, …) |

All four backends fold this one stream: simulate sums it, validate checks it, gcode lowers it, plot
tessellates it. No backend keeps its own forward state-walk.

### 1.1 Segment

Source of truth: `fullcontrol/ir/toolpath.py` (`@dataclass(frozen=True) class Segment`).

| field | type | units | meaning |
|-------|------|-------|---------|
| `start` | `[x,y,z]` (any axis may be `null`) | mm | move start (absolute); a `null` axis means "unchanged / inherited" |
| `end` | `[x,y,z]` | mm | move end (absolute) |
| `travel` | bool | — | `true` = non-extruding travel move |
| `speed` | float | **mm/min** | feedrate (the g-code `F` value) |
| `length` | float | mm | path length (chord for a line, arc length for an arc) |
| `deposited_volume` | float | mm³ | material volume laid down over this move |
| `filament_length` | float | mm | filament consumed (the `E` value) |
| `source_index` | int | — | provenance: index of the design step that produced this segment (or, for parsed g-code, the 1-based source line number) |
| `kind` | `"line"` \| `"arc"` | — | geometric primitive |
| `centre` | `[cx,cy]` \| `null` | mm | arc centre (arcs only) |
| `clockwise` | bool | — | arc direction → `G2` (true) / `G3` (false) |
| `width` | float \| `null` | mm | bead width (`null` when unknown, e.g. parsed external g-code) |
| `height` | float \| `null` | mm | bead height / layer height |
| `color` | `[r,g,b]` \| `null` | 0–1 | display colour (plot only) |
| `arc_points` | `[[x,y,z],…]` \| `null` | mm | tessellated points for an arc (plot/analysis convenience) |

**Native arcs are a first-class primitive** (`kind:"arc"` with `centre`/`clockwise`) — a differentiator
versus every slicer IR, which stores only polylines and arc-fits as a g-code post-process. A scalloped
vase is a handful of arc segments, not hundreds of lines.

### 1.2 MaterialEvent

| field | type | units | meaning |
|-------|------|-------|---------|
| `deposited_volume` | float | mm³ | volume added in place |
| `filament_length` | float | mm | filament consumed |
| `source_index` | int | — | provenance |
| `speed` | float \| `null` | mm/min | feedrate for the emitted line |

### 1.3 Pass-through step

`{"k":"step","type":"<fc class name>","data":{…}}` — any non-motion design step (`Hotend`, `Buildplate`,
`Fan`, `Extruder`, `Acceleration`, `Jerk`, `PressureAdvance`, `ManualGcode`, `PrinterCommand`, …) carried
verbatim by class name + its field dump, rebuilt into the `fc.*` class on read (unknown classes are kept
as the raw dict so nothing is silently lost).

## 2. Serialised form

`fullcontrol/ir/serialize.py` — `to_dict` / `to_json` / `from_dict` / `from_json`. Floats are full
precision so a consumer reproduces identical output; a `null` axis round-trips to `None`.

### 2.1 Version 1 (default)

```json
{"version": 1, "events": [ {"k":"segment", …}, {"k":"material", …}, {"k":"step", …} ]}
```

This is the version emitted by default (`SCHEMA_VERSION == 1`), byte-for-byte stable, so existing
consumers (the Rust kernel, wasm, cached files, p3d) are never disturbed.

### 2.2 Version 2 (opt-in: `to_dict(tp, version=2, …)`)

Version 2 prepends a **purely additive, self-describing header** onto the *identical* `events` stream —
it changes no event, so any consumer that reads only `events` keeps working unchanged (the Rust kernel
reads `ir["events"]` and ignores everything else; verified: v1 and v2 produce identical kernel metrics).

```json
{
  "version": 2,
  "units": {"length":"mm","speed":"mm/min","volume":"mm^3","flow":"mm^3/s","temperature":"degC","angle":"deg"},
  "generator": "fullcontrol <version>",
  "provenance": {"design": "spiral_vase", "params": {"lobes": 5}} ,
  "invariants": ["non_negative_extrusion", "monotonic_layer_z"],
  "events": [ … identical to v1 … ]
}
```

- **`units`** — the fixed FullControl conventions made explicit (UCUM-style codes). The IR has always
  used these; v2 just stops them being tribal knowledge, so a non-Python consumer is self-sufficient and
  a verifier can reject unit confusion at the boundary.
- **`generator`** — the producing tool + version.
- **`provenance`** — *what produced this toolpath* (design name + parameters). This makes
  `reverse_engineer()` / `identify()` exact rather than inferred: if provenance is present, the design is
  known, not guessed.
- **`invariants`** — names from the recognised vocabulary (§3) this toolpath is *declared* to satisfy.

`from_dict` accepts versions in `SUPPORTED_VERSIONS == (1, 2)`; `LATEST_SCHEMA_VERSION == 2`.

## 3. Invariants vocabulary

The v2 `invariants` list declares **checkable intent**. Each name maps onto an existing checker — the
`validate` backend or a `fullcontrol.gcode_engine.verify_gcode` rule — so a declared invariant is not
decorative: it can be enforced.

| invariant | meaning | checked by |
|-----------|---------|-----------|
| `non_negative_extrusion` | no segment retracts via `deposited_volume < 0` | `retraction_balance` |
| `monotonic_layer_z` | z never steps down within the build | negative-z / first-layer rules |
| `within_build_volume` | all coordinates inside the declared build volume | bounds rule |
| `no_cold_extrusion` | no extrusion before the hotend is hot | `cold_extrusion` |
| `bounded_flow` | volumetric flow under the process ceiling | `flow_rate_ceiling` |

(Defined as `INVARIANTS` in `serialize.py`; emitting an unrecognised name raises.) A future
`check_invariants(toolpath)` helper can run the declared set and return per-invariant pass/fail; today
the same checks are reachable via `fc.verify_gcode` on the lowered g-code.

## 4. Columnar form (the binary/zero-copy ABI)

`fullcontrol/ir/columnar.py` is a struct-of-arrays (`numpy`) view of the segment stream — start/end as
`N×3` arrays, plus `travel`/`speed`/`length`/`deposited_volume`/`filament_length`/`width`/`height`. This
is the Arrow-like layout the Rust kernel folds over and the vectorised simulate/validate fast-path. It is
the **performance form of the same IR**; the JSON above is the **interchange form**. (Roadmap: document
the columnar layout as a spec'd, language-neutral binary encoding alongside the JSON — see prior-art's
Apache Arrow recommendation.)

## 5. Versioning & compatibility policy

- **Additive, backward-compatible by default.** New optional fields/headers do not bump the major
  contract; `version` increments only for a richer *understood* shape, and old versions stay readable.
- **`SCHEMA_VERSION` (default-emitted) advances only when consumers are ready.** v1 remains the default
  wire format until the Rust kernel, wasm and p3d explicitly opt into v2; until then v2 is request-only.
  Because v2 is a pure superset header, the migration is risk-free for `events`-only consumers.
- **Unknown pass-through step classes** are preserved as raw `{type,data}` — forward-compatible.

## 6. Interoperation (import / export, not adopt)

The IR is the internal representation; it *lowers to* and *lifts from* external formats:

- **G-code** — the primary backend (lower) and, via `fc.parse_gcode`, the lift (g-code → IR). Native arcs
  lower to `G2`/`G3`. This is the universal transport.
- **3MF Toolpath extension** *(roadmap)* — the strategic interchange/archive target as it matures (it is
  currently unreleased and linear-only; FullControl's arc-native algorithmic layer is positioned as the
  design front-end that lowers into 3MF Toolpath). Push for arc primitives there.
- **STEP-NC (ISO 14649)** *(philosophical alignment only)* — carry intent + working-step structure; do
  not adopt the wire format.
- **Mesh/geometry in** (STL / 3MF / AMF) *(roadmap)* — geometry-in, toolpath-out hybrid design.

## 7. Consumers

- **Python backends** — gcode / plot / simulate / validate fold the in-memory `Toolpath`.
- **Rust kernel** (`rust_kernel/`, PyO3 + wasm) — consumes the JSON for `resolve`/`simulate`/`emit_gcode`/
  `parse_gcode`/`simulate_from_ir`; reads `events`, ignores the v2 header.
- **Browser (wasm)** — `parse_gcode` → `simulate_from_ir` entirely client-side.
- **The engine** — `fc.verify_gcode` / `fc.optimise_gcode` operate on lifted IR.
- **p3d / external tools** — the serialised IR is the cross-tool boundary.

## 8. Non-goals

- Not a CAD/B-rep or mesh format (it is downstream of geometry — it represents *toolpaths*).
- Not a real-time execution/motion-queue format (that is the firmware's job; the IR is design-time).
- Not a machine-control language (g-code remains the transport).

## 9. What is novel here

A **typed, units-aware, multi-language, provenance-carrying IR for *algorithmic* additive toolpaths that
are arc-native, non-planar and variable-width, with IR→IR optimisation and built-in simulate/verify** —
lowering to g-code today and to 3MF Toolpath as it stabilises. The standards survey
(`docs/ir_prior_art.md`) finds no released format occupying this niche: slicer IRs stop at planar
polylines, 3MF Toolpath is unreleased + linear-only, STEP-NC is subtractive, and code-CAD shares kernels
rather than a toolpath IR.
