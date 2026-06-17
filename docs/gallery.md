# Gallery — reimplemented demos & a roadmap

The `examples/` package holds the classic fullcontrol.xyz / `models/` demos reimplemented as clean,
parametric, **importable** functions. Each returns a self-contained `list` of FullControl steps (it
includes its own `ExtrusionGeometry`), so it runs through any backend with no extra setup:

```python
import fullcontrol as fc
from examples import wave_bowl

steps = wave_bowl(opening_radius=25, rim_waves=6)
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='generic', initialization_data={'nozzle_temp': 210, 'bed_temp': 40,
                                                  'primer': 'front_lines_then_y'}))
```

Every design is covered by `tests/unit/test_examples.py` — each resolves to gcode, simulates to a
real print (time/material > 0), and validates with no errors against a 200³ build volume.

## Catalogue

| design | technique | what it shows | default print (generic, ~`sim`) |
|---|---|---|---|
| **spiral_vase** | vase-mode helix | the seamless single-wall spiral everything else builds on; optional radial `lobes` flute it | ~16k segs, ~12 min |
| **ripple_vase** | vase-mode + superimposed radial modulation | three stacked effects on one running parameter — fast `ripples`, slow `star_tips`, height-driven `bulge` — give the woven star texture (reimplements `ripple_texture`) | ~12.6k segs, ~20 min |
| **nonplanar_spacer** | non-planar concentric rings | z varies *within* each ring (sinusoidal `waves`) so the whole washer is one ramped non-planar spiral; needs a pointy nozzle (reimplements `nonplanar_spacer`) | ~1.5k segs, ~1 min |
| **wave_bowl** *(new)* | curved wall profile + ramped rim wave | combines a flaring `sin` wall profile with a rim ripple whose amplitude grows as height² — clean base, wavy lip | ~13.3k segs, ~10 min |
| **gyroid_infill** *(new)* | continuous gyroid-TPMS weave | one seamless bead (zero travels/retractions) — per-layer sine serpentine whose phase shears with z and whose direction alternates each layer, interlocking like a gyroid | ~10k segs, ~9 min |
| **twisted_polygon_vase** *(new)* | rotating / morphing polygon cross-section | a regular n-gon cross-section that twists with height and can morph to a different vertex count (e.g. pentagon → octagon), as one continuous spiral | ~21k segs @40mm |

### Export: self-contained 3D viewer (`result_type='3d_html'`)
```python
html = fc.transform(steps, '3d_html', fc.PlotControls(color_type='z_gradient',
       initialization_data={'save_as': 'design', 'title': 'My Vase'}), show_tips=False)
```
Resolves the design to the same `PlotData` the Plotly preview uses, then writes a **single
self-contained HTML file**: an interactive WebGL viewer (three.js from a pinned CDN via importmap)
with orbit controls, the toolpath as vertex-coloured lines (travels dimmed), a bed grid and an info
overlay. The geometry is embedded in the page, so the file opens in any browser and can be shared as
one document. `save_as` (via `initialization_data`) writes `<name>.html`; the runner also returns the
HTML string.

### Analysis tool (not a printable design)
**`print_time_study.sweep(design_fn, param, values, **fixed)`** simulates a design once per
parameter value and returns the metrics; `study_table()` formats them and `study_figure()` returns a
Plotly chart of print time and material against the parameter. Built on the `simulation` backend
(now the Rust kernel), so sweeping many large designs is fast — e.g. 8 full ripple vases (151k
segments total) simulate in ~370 ms. Useful for spotting trade-offs: sweeping `extrusion_width`, for
instance, shows print time staying flat while filament use climbs.

### Validator showcase (not a printable design)
**`validation_gauntlet()`** returns a `dict[str, list]` of twelve tiny designs, each crafted to trip
exactly one pre-flight validation rule (out-of-bounds, negative-z, cold-extrusion, nozzle/bed temp,
zero/fast speed, first-layer-z, unbalanced retraction, zero geometry, stringing). Companion dicts
`INIT` (the `initialization_data` each needs) and `EXPECTED` (`rule -> (severity, substring)`) make it
self-checking and turn the validator into living documentation — run any entry through the `validate`
backend to see exactly the message it demonstrates.

Each function is fully parametric — see its docstring for the knobs (radius/height/wave counts/twist
/flare/etc.). Run a module directly (`python -m examples.wave_bowl`) to drop a `.gcode` next to it.

### Design idioms these demonstrate
- **One running parameter.** A single `frac` (turns completed) drives angle, height and every radial
  modulation — superimpose effects by just adding terms to the radius.
- **Self-contained designs.** Embedding `ExtrusionGeometry` in the step list (rather than only via
  `GcodeControls`) makes a design portable across `gcode`/`plot`/`simulation`/`validate`.
- **Non-planar = vary z mid-path.** `nonplanar_spacer` and `wave_bowl` move z *within* a revolution,
  which is exactly what slicer-based workflows can't express.

## Roadmap — what else can be created

Grouped by what each would exercise in the library. The ones marked **(needs …)** point at a small
library gap worth closing first.

### A. More parametric geometry (pure design — no library change)
- ✅ **Gyroid / TPMS infill block** — *done* (`gyroid_infill`): a single continuous toolpath
  approximating a gyroid surface; the poster-child for "impossible to slice" designs.
- ✅ **Twisted polygon vase** — *done* (`twisted_polygon_vase`): an n-gon cross-section that twists
  with height and can morph to a different vertex count (pentagon→octagon).
- **Helical screw / auger** — a flighting surface as a spiral ramp; tests steep-overhang printing.
- **Möbius strip / trefoil band** — a closed non-planar ribbon (parametric centre-line + width).
- **Lattice cylinder** — diagonal helices in both directions forming a printable diamond lattice
  (generalises `star_polygon_lattice`).
- **Coaster / texture tile pack** — flat tiles with hilbert-curve, truchet, and concentric-wave fills
  — a quick way to show 2D infill patterns.
- **Parametric funnel / nozzle adapter** — two different-diameter circular ports joined by a swept
  profile (generalises `hex_adapter`).

### B. Toolpath-quality designs (exercise the optimization passes)
- **Bridged box** — long travels over openings that `retract_on_travel` should guard; a regression
  fixture for the anti-stringing pass.
- **Coasting/z-hop showcase** — a design tuned to make `coasting` and `z_hop` visibly improve seams,
  with before/after `simulation` peak-flow numbers.

### C. New library capability (design + a feature)
- **Variable-width line art** — per-segment `ExtrusionGeometry.width` driven by a function, for
  calligraphic single-wall art. *(needs: nothing — already supported; just no demo.)*
- **Multi-material / tool-change demo** — alternating regions on a toolchanger. *(needs: a richer
  tool-change story than the current `T0`/`T1` manual gcode.)*
- **Sequenced multi-object plate** — N copies with per-object purge, laid out on a grid. *(uses
  `fc.move(copy=True)`; pairs well with a future travel-reordering pass.)*
- **Conical / cylindrical non-planar mapping** — wrap a flat pattern onto a cone or cylinder via a
  reusable coordinate transform. *(needs: a `geometry` transform helper — generalises what
  `nonplanar_spacer` does by hand.)*

### D. Backend-showcase designs
- ✅ **Print-time/material study** — *done* (`print_time_study`): one shape swept over a parameter,
  charting `simulation` output — exercises the Rust-kernel simulate fast-path on many large designs.
- ✅ **Validation gauntlet** — *done* (`validation_gauntlet`): twelve designs that each trip one
  validation rule — living documentation of the checks.

**Done so far:** `gyroid_infill`, `validation_gauntlet`, `twisted_polygon_vase`, `print_time_study`.
**Suggested next:** the **helical screw / auger** (steep-overhang test) and the **surface-conforming
transform helper** (section C — enables a whole class of conical / cylindrical-mapped designs).
