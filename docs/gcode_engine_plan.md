# G-code Verification & Optimisation Engine — design & implementation plan

## Why

Today everything flows **design → IR → g-code** (forward). There is **no g-code → IR parser**. A
verification/optimisation engine needs to ingest *arbitrary* g-code (our own output and other slicers')
lift it back to the IR, then verify and optimise it. The parser is the foundation everything builds on.

## Where it plugs in (existing architecture)

```
steps → resolve()  → Toolpath{events: Segment | MaterialEvent | pass-through step}
      → apply_passes()  (fullcontrol/ir/passes.py)
      → gcode_from_ir() (fullcontrol/gcode/dialect.py)  ≡  emit_gcode() (rust_kernel/src/gcode.rs, byte-identical)
```

- **Joint 1 — the IR JSON schema** (`fullcontrol/ir/serialize.py`, SCHEMA_VERSION=1). The new parser
  produces a `Toolpath` structurally identical to `resolve()`'s output, so every existing pass,
  validator and simulator consumes it unchanged. Segment fields: `start/end` (None-safe abs coords),
  `travel`, `speed`, `length`, `deposited_volume`, `filament_length`, `source_index`, `kind`
  (`line`|`arc`), `centre`/`clockwise`, `width`/`height`, `color`, `arc_points`.
- **Joint 2 — the backend registry** (`combinations/gcode_and_visualize/common.py`). New result types
  `'verify_gcode'` and `'optimise_gcode'` register alongside `gcode`/`simulation`/`validate`.
- **Rust hot path** — the kernel already emits g-code (`gcode.rs`) and compiles to PyO3 *and* wasm
  (`python_api.rs` / `wasm_api.rs`). A new `parser.rs` mirrors the emitter (gcode → IR JSON). A
  pure-Python reference parser is the source of truth (and the wasm/no-kernel fallback), exactly like
  `ir/kernel.py:resolve_columnar_rust` falls back today.

## New package layout

```
fullcontrol/gcode_engine/
  parser.py        gcode → Toolpath IR (inverse of dialect.py); reference impl + Rust dispatch
  detector.py      ParseParams + dialect/flavor detection (Marlin/Klipper/Duet, rel vs abs E, units, dia)
  verification.py  Issue{severity, rule, message, line, segment_index, suggested_fix} + VerificationReport
  rules/           geometry.py, extrusion.py, travel.py, adhesion.py, thermal.py
  passes/          arc_fit.py, travel_reorder.py, adaptive_speed.py, simplify.py
  optimiser.py     apply_passes + before/after simulate → OptimisationReport
  public.py        verify_gcode(text)→report ; optimise_gcode(text, passes)→(text, report) ; parse_gcode(text)→Toolpath
  cli.py/__main__  python -m fullcontrol.gcode_engine verify|optimise|inspect
rust_kernel/src/parser.rs   gcode text → IR JSON (PyO3 + wasm)
```

`ParseParams` is a plain dataclass (not a pydantic step): `flavor`, `relative_e`, `e_units` (`mm`|`mm3`),
`dia_feed`, `travel_g1_e0`, with `.detect(text)` and `.from_controls(controls)`.

## 1. The parser (inverse of the dialect)

Stateful line scanner holding the same running context as `resolve()`/`walk.rs` — position cursor,
extruder on/off, speed, E accumulator, E-mode + volume↔E ratio. Per line: strip `;` comment, tokenise
`G/X/Y/Z/E/F/I/J/R`, dispatch.

- **Motion:** `G0` travel; `G1` extrude/travel by ΔE sign; `G2`/`G3` arc (centre = start+I,J; arc length
  via existing `arc_geometry`); `G28` home; `G92 E0` reset accumulator (no segment); `G90/G91`.
- **M-codes → pass-through events:** `M104/M109→Hotend`, `M140/M190→Buildplate`, `M106→Fan`,
  `M82/M83→Extruder(relative_gcode)`, `M204→Acceleration`, `M205`/`SET_VELOCITY_LIMIT→Jerk`,
  `M900 K`/`SET_PRESSURE_ADVANCE→PressureAdvance`, unknown → `ManualGcode(text=line)`.
- **E → filament_length** uses `volume_to_e` from `dia_feed`/`units`, mirroring
  `ExtruderState.update_e_ratio`. **`width`/`height` cannot be recovered from E alone** (one equation,
  two unknowns) → `None` unless slicer comments (`;WIDTH:`/`;HEIGHT:`/`;LAYER_HEIGHT:`, which Prusa/Cura/
  Bambu write) supply them; the detector extracts those.
- **Round-trip guarantee (correctness anchor):** for our own output,
  `emit(parse(fc.transform(steps,'gcode'))) == fc.transform(steps,'gcode')` byte-for-byte. This pins the
  parser to the emitter the way `test_columnar.py` pins the resolvers.
- **Lossy from external slicers:** `source_index` (repurposed as 1-based gcode line number), `width`/
  `height` (only from comments), `color` (always None), `arc_points` (rebuilt from centre/clockwise).
- Parser **never panics**: unparseable line → `ManualGcode`; bad coordinate → inherit previous + a
  `parse_warning`.

## 2. Verification layer

Reuse all 8 existing `validate/run.py` rules over the lifted IR via a new internal
`validate_toolpath(toolpath, params, result)` entry point (public `validate(steps, controls)` stays
unchanged). Add rules tuned for external g-code, each emitting `Issue` with `line` + `segment_index`:

- `overhang_angle` — extruding XY beyond the previous layer's hull by >½ line width (approx; suggests
  "provide source mesh for precise analysis").
- `flow_rate_ceiling` — vectorised `deposited_volume / (length/speed*60)` > `max_flow_mm3s` (def 15 for
  0.4mm).
- `over_extrusion` — when width/height known, `deposited_volume/length` outside `[0.5,1.5]·width·height`.
- `first_layer_adhesion` — first-layer speed ≤ 50% of later layers; first-layer z ≤ layer height.
- `travel_density` — `travel/extruding` > 0.3 → suggests `travel_reorder`.
- `cooling_sanity` — fan still 0 after the first layer.
- `seam_clustering` — layer-change XY scatter > 5mm (visible seam scar).
- `arc_opportunity` — >4 consecutive segments fit a common circle within 0.05mm → suggests `arc_fit`.

`VerificationReport`: `issues`, `parse_params`, optional inline `SimulationResult`, with
`.errors/.warnings/.ok/.summary()/.raise_if_errors()` (superset of `ValidationResult`; kept as a new
dataclass to avoid a breaking pydantic schema change). Non-planar g-code (>50% of moves change z) →
`info` notice that overhang/seam rules are disabled.

## 3. Optimisation layer

Existing passes (`merge_collinear`, `retract_on_travel`, `coasting`, `z_hop`) work unchanged on a parsed
Toolpath. New passes, each with a stated invariant (physical print unchanged unless intended; new
`Segment`s constructed, since `Segment` is frozen):

- `arc_fit` — sliding window of extruding lines → single `kind='arc'` G2/G3 when they fit a circle within
  tolerance (def 0.05mm); volume conserved; tight/short curves left as lines.
- `travel_reorder` — nearest-neighbour + 2-opt over extrusion "islands" within a z-layer; island internals
  byte-identical; travel distance/time reduced; no cross-layer reordering (seam/collision risk).
- `adaptive_speed` — scale `speed` down at high-curvature corners / overhang segments (clamped); only F
  changes, material unchanged.
- `simplify` — Ramer–Douglas–Peucker on straight runs within tolerance (def 0.01mm); material conserved.

`optimise_gcode` wraps `apply_passes` with before/after `simulate` → `OptimisationReport`
(`PassResult` per pass: segments/time/volume before↔after).

## 4. Public surface

```python
fc.verify_gcode(text, *, params=None, rules=None, simulate=True, build_volume=None, max_flow_mm3s=15) -> VerificationReport
fc.optimise_gcode(text, passes=None, *, params=None, return_report=True) -> str | (str, OptimisationReport)
fc.parse_gcode(text, params=None) -> Toolpath
```

Plus a CLI: `python -m fullcontrol.gcode_engine verify|optimise|inspect file.gcode [--rules …] [--passes …]
[--build-volume X,Y,Z] [--json] [-o out.gcode]` (reads stdin on `-`). **WASM angle:** add `parse_gcode`
+ `simulate_from_ir` to `wasm_api.rs` → browser does parse → simulate → metrics client-side (numpy rule
checks remain server/CLI-side — a deliberate scope boundary).

## 5. Phased roadmap (each phase = a shippable PR, TDD)

1. **Python parser + round-trip** (foundation). `parser.py`, `detector.py`, re-export `parse_gcode`.
   Tests: round-trip every `GcodeControls` variant (generic/marlin-rel/marlin-abs/klipper/duet) byte-zero;
   arcs; M-code pass-throughs; absolute-E with `G92 E0`; detector header/relative/volumetric detection.
2. **Rust parser + parity.** `parser.rs` (+`lib.rs`/`python_api.rs`/`wasm_api.rs`), Python dispatch with
   fallback. Tests: Rust↔Python IR field-by-field parity on golden fixtures; 50k-line file < 200ms.
3. **Verification layer.** `verification.py` + `rules/*`, `verify_gcode`, register backend, extract
   `validate_toolpath`. Tests: rule-by-rule (cold-extrusion, out-of-bounds w/ line no., flow ceiling w/
   segment idx, arc opportunity), no-false-positives on our own tutorial gcode, simulation attached.
4. **Optimisation passes + optimiser.** 4 new passes + `optimise_gcode` + backend. Tests: per-pass
   invariants (arc_fit conserves material & emits G2/G3; travel_reorder reduces travel & preserves island
   internals; adaptive_speed lowers corner speed; simplify conserves material); optimise round-trips.
5. **CLI + API polish.** `cli.py`/`__main__.py`, top-level re-exports. Tests: exit codes, output file,
   `--json` validity.
6. **WASM integration.** `parse_gcode` + `simulate_from_ir` in `wasm_api.rs`. Test: headless wasm parse →
   simulate → `segment_count > 0`.

## Key trade-offs

- **Always parse→IR→emit** (vs string-level edits): heavier, but every pass gets full IR (speeds/volumes/
  arcs) and composes with simulate for before/after metrics; Rust fast-path mitigates cost on big files.
- **New `VerificationReport`** (vs extending `ValidationResult`): avoids a breaking pydantic schema change;
  superset semantics.
- **`source_index` repurposed as line number**: cheapest provenance path (no schema bump); no functional
  consumer reads it today. If both are ever needed, bump SCHEMA_VERSION to 2.
- **Travel reorder limited to within a layer**: cross-layer changes seam/needs support knowledge.
- **Overhang without a mesh**: layer-n vs layer-(n-1) extent comparison — approximate, flagged as such;
  precise analysis would accept an optional STL.
