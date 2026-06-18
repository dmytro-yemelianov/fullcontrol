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

### 2.1 Version 1 (lean shape, on request)

```json
{"version": 1, "events": [ {"k":"segment", …}, {"k":"material", …}, {"k":"step", …} ]}
```

The headerless shape, available via `to_dict(tp, version=1)` for any consumer that wants the minimal
form. `from_dict` always accepts it.

### 2.2 Version 2 (the default)

Version 2 (emitted by default, `SCHEMA_VERSION == 2`) prepends a **purely additive, self-describing
header** onto the *identical* `events` stream — it changes no event, so any consumer that reads only
`events` keeps working unchanged (the Rust kernel reads `ir["events"]` and ignores everything else;
verified: v1 and v2 produce identical kernel metrics, so g-code/simulation output is unchanged).

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

(Defined as `INVARIANTS` in `serialize.py`; emitting an unrecognised name raises.) The declaration is
**enforceable**, not decorative: `fullcontrol.ir.check_invariants(toolpath, names, build_volume=…,
max_flow=…)` folds the IR event stream and returns an `InvariantReport` (`.ok` / `.all_checked` /
`.summary()` / `.raise_if_violated()`), with each result listing the offending event indices. Invariants
that need a parameter (`within_build_volume` → `build_volume`, `bounded_flow` → `max_flow`) report
`checked=False` (vacuously ok) when it is absent, so declaring an invariant you cannot yet check is safe.
For the v2 flow, pass the declared list straight through:

```python
from fullcontrol.ir import from_dict, check_invariants
d = ...                                   # a v2 IR dict
report = check_invariants(from_dict(d), d.get('invariants') or [], build_volume=(200, 200, 200))
report.raise_if_violated()
```

The same checks remain reachable via `fc.verify_gcode` on lowered g-code; `check_invariants` is the
IR-level counterpart.

**`transform` self-verifies on request.** Declaring `invariants` in `initialization_data` makes
`fc.transform` resolve the design once and check them before running *any* backend, so a design guards
itself:

```python
fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='generic',
    initialization_data={'nozzle_temp': 210, 'build_volume_x': 200, 'build_volume_y': 200,
                         'build_volume_z': 200,
                         'invariants': ['monotonic_layer_z', 'within_build_volume'],
                         'invariant_mode': 'raise'}))   # 'raise' (default) | 'warn'
```

It is off by default (no `invariants` key → no-op, output unchanged), mirroring the
`initialization_data['optimize']` opt-in. `build_volume` (for `within_build_volume`) and `max_flow`
(for `bounded_flow`) come from `initialization_data`; an invariant whose parameter is absent is skipped.

## 4. Columnar form (the binary/zero-copy ABI)

`fullcontrol/ir/columnar.py` is a struct-of-arrays (`numpy`) view of the segment stream — start/end as
`N×3` arrays, plus `travel`/`speed`/`length`/`deposited_volume`/`filament_length`/`width`/`height`. This
is the Arrow-like layout the Rust kernel folds over and the vectorised simulate/validate fast-path. It is
the **performance form of the same IR**; the JSON above is the **interchange form**. (Roadmap: document
the columnar layout as a spec'd, language-neutral binary encoding alongside the JSON — see prior-art's
Apache Arrow recommendation.)

### 4.1 Binary encoding (the spec'd columnar form)

`fullcontrol/ir/binary.py` — `to_bytes(tp, *, provenance=None, invariants=None) -> bytes`,
`from_bytes(data) -> Toolpath`, `read_header(data) -> dict`. A compact, little-endian, self-describing
container that round-trips the **same** `Toolpath` as the JSON (segments + material events + pass-through
steps) but stores the hot numeric columns as raw Arrow-shaped arrays instead of per-event JSON objects.
For a several-thousand-segment design it is **~3.8× smaller** than the v2 JSON (measured on a 6000-segment
spiral vase: 661 KB vs 2.54 MB) — no key names, no decimal text, raw `float64` columns.

**Layout** (all multi-byte values little-endian):

```
magic        4 B     b'FCIR'
format_ver   uint16  binary container format version (1)
flags        uint16  reserved, 0
meta_len     uint32  byte length of the metadata block
meta         JSON    UTF-8 metadata (below)
<columns>            contiguous arrays in meta['columns'] order, at meta['offsets'][name]
```

The metadata block (JSON) carries the **v2 header** (`units` / `generator` / `provenance` / `invariants`),
the `schema_version`, per-event-kind counts, and — crucially — the layout: `columns` (names, in order),
`offsets`/`nbytes` (byte position + size of each column), `event_order` (one tag per event — `s`egment,
`m`aterial, `p`ass-through-step — so the print-order interleaving is reconstructed exactly), plus the JSON
*tail* for the rare/ragged data: `steps` (pass-through steps by `{type,data}`) and `seg_extra` (per-arc
`centre`/`clockwise`/`arc_points` and per-move `color`, keyed by segment row index).

**Columns**, packed back-to-back after the metadata, one contiguous block each:

| column | dtype | per row | null encoding |
|--------|-------|---------|---------------|
| `start`, `end` | float64 | 3 (x,y,z) | a `None` axis → `NaN` |
| `travel` | uint8 | 1 | — (1/0) |
| `speed`, `length`, `deposited_volume`, `filament_length`, `width`, `height` | float64 | 1 | `None` → `NaN` (width/height) |
| `source_index` | int64 | 1 | — |
| `kind` | uint8 | 1 | 0 = line, 1 = arc |
| `material` | float64 | 4 (`deposited_volume`, `filament_length`, `source_index`, `speed`) | speed `None` → `NaN` |

**Design rationale.** This is the Apache-Arrow recommendation from `docs/ir_prior_art.md` made concrete:
the numeric heart of the segment stream — exactly the struct-of-arrays of `columnar.ColumnarToolpath` —
is written with `numpy.tobytes()` and read with `numpy.frombuffer` (near-zero-copy on read, no per-value
parsing). `NaN` marks a null axis or undefined width/height, mirroring `columnar.py`, and `from_bytes`
maps `NaN` back to `None` so `(None, None, None)` round-trips. The **rare and irregular** fields (pass-through
steps, arc geometry, colours) go in the JSON tail rather than as sparse fixed columns — keeping the hot,
uniform columns binary while preserving full JSON-equivalent fidelity (pass-through steps rebuild into their
`fc.*` class, unknown classes kept as the raw dict). The header's `columns`/`offsets`/`nbytes`/counts make
the layout fully recoverable by any reader, in any language.

**Caveats.** The format is fixed little-endian (`to_bytes` forces it; `from_bytes` byte-swaps on a
big-endian host, so cross-endian round-trips are correct). Material `source_index` is stored via `float64`
(exact for indices `< 2^53`); segment `source_index` is `int64`. Pass-through-step handling is identical to
the JSON form, so binary and JSON share the same fidelity and the same unknown-class behaviour.

## 5. Versioning & compatibility policy

- **Additive, backward-compatible by default.** New optional fields/headers do not bump the major
  contract; `version` increments only for a richer *understood* shape, and old versions stay readable.
- **`SCHEMA_VERSION` (default-emitted) is 2.** v2 is a pure superset header over the v1 `events` stream,
  so the switch is risk-free for any `events`-only consumer (the Rust kernel, wasm). Consumers that want
  the lean form request `to_dict(tp, version=1)`; `from_dict` accepts both.
- **Unknown pass-through step classes** are preserved as raw `{type,data}` — forward-compatible.

## 6. Interoperation (import / export, not adopt)

The IR is the internal representation; it *lowers to* and *lifts from* external formats:

- **G-code** — the primary backend (lower) and, via `fc.parse_gcode`, the lift (g-code → IR). Native arcs
  lower to `G2`/`G3`. This is the universal transport.
- **3MF Toolpath extension** *(experimental — implemented; see §6.1)* — the strategic interchange/archive
  target as it matures (it is currently unreleased and linear-only; FullControl's arc-native algorithmic
  layer is positioned as the design front-end that lowers into 3MF Toolpath). Push for arc primitives there.
- **STEP-NC (ISO 14649)** *(philosophical alignment only)* — carry intent + working-step structure; do
  not adopt the wire format.
- **Mesh/geometry in** (STL / 3MF / AMF) *(roadmap)* — geometry-in, toolpath-out hybrid design.

### 6.1 3MF Toolpath interop *(experimental)*

`fullcontrol/ir/threemf.py` implements a **best-effort** export/import against the 3MF
Toolpath / Laser-Toolpath extension **draft** (namespace
`http://schemas.microsoft.com/3dmanufacturing/toolpath/2019/05`,
<https://github.com/3MFConsortium/spec_lasertoolpath>). The draft is unreleased and its OPC packaging
is under-specified, so this is a *tracking* implementation, not a ratified format — the element/
attribute **names** follow the draft; the exact container bytes are a clean, documented approximation.
Exported as `fc.to_3mf` / `fc.from_3mf` (also `fullcontrol.ir.to_3mf` / `from_3mf`). Stdlib only
(`zipfile` + `xml.etree.ElementTree`).

```python
to_3mf(toolpath, path, *, layer_height=None) -> None    # export to an OPC ZIP .3mf
from_3mf(path) -> Toolpath                               # import back to IR Segments
```

**Parts written** (the OPC/ZIP container):

| part | content |
|------|---------|
| `[Content_Types].xml` | OPC content-type map (model + toolpath-layer + rels) |
| `_rels/.rels` | package root → the 3D model part (3MF startpart relationship) |
| `3D/3dmodel.model` | 3MF core `<model>` (minimal valid build) **+** `<tp:toolpathresource>` with `<tp:toolpathprofiles>` and `<tp:toolpathlayers>` |
| `3D/_rels/3dmodel.model.rels` | model → each layer part (`…/2019/05/toolpath` relationship type) |
| `3D/toolpath/layer_NNNNN.xml` | one per Z layer: `<layer>` → `<parts>`/`<profiles>`/`<data>`/`<segments>` of `<segment type="polyline">` holding `<point x= y=>` device-unit coords |

Bead geometry and speed ride on `<toolpathprofile>` via the draft's `beadwidth` / `beadheight` /
`depositionspeed` attributes; each segment references its profile by id (one profile per distinct
`(width, height, speed)`). Coordinates are stored as **integer device units**; `unitfactor` (default
`1e-3` mm/unit) converts to mm. Layers are bucketed by end-Z (rounded to `layer_height` if given).

**Round-trip fidelity** (`from_3mf(to_3mf(tp))`):

- *Preserved* — the **extruding XYZ path** within device-unit tolerance (X/Y from the points, Z from
  the layer's `ztop`), per-layer segment counts, bead width/height, and speed.
- *Lossy / dropped* — **3MF Toolpath is linear-only, so native arcs are tessellated to line
  segments** (centre/clockwise lost; path *length* preserved); **travel** (non-extruding) moves are
  not written; pass-through steps (temperature/fan/manual g-code) and `StationaryExtrusion` material
  events are dropped; `deposited_volume`/`filament_length` are recomputed from geometry × bead on
  read, not stored. Non-planar designs get **approximate** layering (one Z per bucket).

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
