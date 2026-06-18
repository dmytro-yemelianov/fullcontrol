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
| **helical_screw** *(new)* | helical thread / auger | a rod whose wall carries a triangular thread whose phase advances with angle *and* height (`starts` / `pitch` / `thread_depth`, optional tapering core); shallow = screw, deep+coarse = auger — one seamless spiral | ~26k segs @40mm |
| **textured_cone** *(new)* | flat texture wrapped on a surface of revolution | built on the reusable `revolve(profile, texture, …)` helper — a tapering cone carrying an egg-crate diamond grid; pass your own `profile`/`texture` lambdas to wrap any 2-D pattern onto a cone/cylinder/barrel | ~23k segs @35mm |
| **mobius_band** *(new)* | parametric non-planar art | the classic Möbius surface (one half-twist, one side, one edge); a boustrophedon rasters the twisting ribbon as one continuous bead. *Needs support to print* — an art / visualisation piece | ~7k segs |
| **trefoil_tube** *(new)* | swept knot tube | a single-wall tube spiralled along a trefoil-knot centre-line via a Z-up frame (no Frenet twist); one continuous helical bead that closes on itself. *Needs support* — an art piece | ~9.6k segs |
| **towers_grid** *(new)* | travel-heavy multi-part print | a grid of separate square-wall towers with extruder-off hops between them and subdivided collinear edges — built to exercise the IR→IR **optimization passes** (see below) | varies |
| **hex_adapter** *(new)* | morphing/lattice prism — official model | a faithful reimplementation of FullControl's *Hex Adapter*: a hexagonal-lattice washer (an inner hex port inside an outer hex body) traced as one continuous seam-stitched bead and stacked as a constant prism; flat-to-flat sizes map to circumradii via 2/√3 with oversize/undersize fine-fit. Verified against the published g-code | ~constant prism |
| **lampshade** *(new)* | flaring ribbed vase — official model | a reimplementation of FullControl's *Lampshade*: a tall flaring single-wall shade with `ribs` vertical flutes (cut inward, optionally twisting) on a cone that widens from `internal_hole_radius` by `inner_frame_amplitude`; translucent prints cast light patterns. One seamless support-free spiral | varies |
| **nuts_and_bolts** *(new)* | threaded bolt — official model | a reimplementation of FullControl's *Nuts and Bolts*: a hexagonal head (apothem/cos cross-section) blending into a cylindrical shaft carrying a helical V-thread whose phase advances with angle *and* height (`thread_pitch`/`thread_depth`/`thread_starts`), as one continuous vase-mode spiral. Pitch verified against the published g-code | varies |
| **star_polygon_lattice** *(new)* | tiled star-polygon lattice — official model | a reimplementation of FullControl's *Star-Polygon Lattice*: a `cols×rows` grid of regular star polygons {n/k} (e.g. {5/2} pentagram), each one continuous closed stroke, the whole grid snaked boustrophedon as one flat bead and stacked `layers` high. Verified against the published g-code | flat lattice |
| **phone_stand** *(new)* | adjustable-angle stand — official model | a reimplementation of FullControl's *AnyAngle Phone Stand*: a continuous-Z seamless spiral of a wavy rounded-square tube (~84×84×30mm) that cradles a phone at any lean (`stand_angle`) in portrait or landscape, with a mid-height clamping waist and an "angry mode" that sharpens the corrugations | ~36k segs |
| **pin_support_challenge** *(new)* | tall thin pin — official model | a reimplementation of FullControl's *Pin-Support Challenge*: a spiral base disc → a single thin vertical bead (the support-free pin) → a 45° spiral cone fanned from the pin tip; `conical_start` swaps the flat base for a tapered one. One seamless bead | ~2.7k segs |
| **overhang_challenge** *(new)* | progressive overhang — official model | a reimplementation of FullControl's *Overhang Challenge* (+ *Plus*): a spiral foot → vertical wall → linear **outward flare** that leans the wall progressively into a steep (~75°) unsupported overhang; `plus` swaps the circle for an `sides`-gon and toggles inward/outward lean | ~2.2k segs |
| **arc_vase** *(new)* | native `fc.Arc` (G2/G3) vase | the first gallery design built from true circular **arcs**: each layer is a scalloped/petal cross-section of `petals` tangent `fc.Arc` moves (one G2/G3 each, helical end-z so it climbs as one spiral) — a handful of arc commands per layer instead of hundreds of segments; glass-smooth, tiny g-code. Showcases a capability nothing else in the gallery uses | `petals` arcs/layer |
| **brush_lettering** *(new)* | per-segment variable line width | a flat plaque where one continuous bead traces a stroke whose **width swells and thins like a brush** (fat downstrokes, hairline upstrokes) by emitting a fresh `ExtrusionGeometry(width=…)` along the path — true calligraphic line weight, impossible in a normal slicer. Presets `sine`/`loop`/`signature` or any `width_fn` | single layer |
| **bead_studs** *(new)* | `fc.StationaryExtrusion` stud field | a plate dotted with raised domes built by parking the nozzle and oozing a set volume in place (`StationaryExtrusion`) — laid out as a grid or as grade-1 **braille** (a `message` string → dot patterns). Showcases extrude-in-place, which no other design uses | grid / braille |
| **retraction_test** *(new)* | retraction stress test — official model | a reimplementation of FullControl's *2000-Retractions Test*: a flat serpentine field of short marks where every inter-mark travel is bracketed by an explicit `Retraction`/`Unretraction`, so the print performs a configurable (default many-hundred) number of retractions for calibration | flat field |
| **blob_printing** *(new)* | deliberate blob field — official model | a reimplementation of FullControl's *Blob Printing*: a field of discrete blobs oozed in place with `StationaryExtrusion` (travel extruder-off between sites), with a corner-to-corner size gradient and optional stacked blob towers | grid of blobs |
| **freeform_frosting** *(new)* | swirled frosting column — official model | a reimplementation of FullControl's *Freeform Frosting Challenge*: a vase-mode column that tapers to a soft-serve peak while `swirls` flutes wind around it (phase advancing with height) — piped-frosting look; optional fan/speed ramps up the overhang | ~32×32×50mm |
| **fractional_design_engine** *(new)* | polar curve engine — official model | a reimplementation of FullControl's *Fractional Design Engine (Polar)*: traces a parametric polar curve r(θ) over fractional `turns` — a `petals`-petal rose by default, or an explicit `(radial, angle)` fraction list (reproducing the published alternating star exactly) | flat polar |
| **tape_reinforcement** *(new)* | fibre-reinforcement demo — official model | a reimplementation of FullControl's *Tape-Reinforcement Research Demo*: a flat raster-filled tensile coupon that inserts a `ManualGcode` pause before each `tape_layers` layer so reinforcing tape/fibre can be laid by hand and printed over to embed it | flat strip |
| **snake_soapdish** *(new)* | snake-mode open corrugated wall | a faithful reimplementation of FullControl's *Snake-Mode Soapdish*: an **open** corrugated wall (not a cup) printed in snake mode — print one way, step z up, print back, step up — with a sine-wave footprint of `waves` corrugations and a lens silhouette (widest at mid-height). Fat 1mm lines, hot & fast. Verified against the published g-code (60mm × ~100mm, 8 corrugations) | ~15k segs |

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

### Optimization-pass showcase
**`optimization_report(towers_grid())`** resolves a travel-heavy design with and without the IR→IR
optimization passes (`fullcontrol/ir/passes.py`) and reports the difference. On the default towers
grid: `merge_collinear` collapses the subdivided edges (**580 → 120 segments**), `retract_on_travel`
inserts a retraction around each long inter-tower hop (**0 → 6 retractions**), and the simulation
time/material is **unchanged** — the passes shrink the g-code without altering the physical print.
Passes are opt-in via `initialization_data={'optimize': [...]}`, so default output is never changed.

### Reverse-engineering — g-code → formula
**`reverse_engineer(gcode)`** runs the pipeline *backwards*: it parses a g-code file to extruding
points, decomposes them into cylindrical coordinates about an auto-detected axis, and least-squares-
fits the modulation. The **dominant angular harmonic is the design's lobe / wave count**, its
amplitude the depth, and the radius-vs-z fit gives the cylinder/cone/taper profile. From g-code
*alone* it recovers, e.g., a 5-lobe vase as `r(θ) ≈ 15 + 2·cos(5θ)` and a hexagonal vase as 6 lobes —
exact counts, with `describe()` rendering the formula. Closed-form for the surface-of-revolution /
vase family (most of the gallery); arbitrary 3-D toolpaths are out of scope (symbolic-regression
territory).

**`identify(gcode)`** goes further — it matches the recovered signature against the gallery's *forward*
models and returns the named design + its parameters + a `fit_error` (chamfer mm to the regenerated
design). It recovers the exact family and counts, exact radius/depth for the cosine vase, and the
polygon's circumradius (distinguishing a polygon from a sine-lobed vase by its higher harmonics). The
**Snake-Mode Soapdish is an open corrugated wall, not a surface of revolution** — `identify` detects it
because snake mode holds z constant within each course (vases spiral z continuously) and recovers its
corrugation count, length and height directly. E.g. a 5-lobe vase ->
`spiral_vase(radius=15, lobes=5, lobe_depth=2)` at 0.23 mm fit error; the published Snake-Mode Soapdish
g-code -> `snake_soapdish(length=60, height=100, waves=8, …)` at ~3.8 mm.

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
- ✅ **Helical screw / auger** — *done* (`helical_screw`): a helical thread (screw → auger via
  depth/pitch/taper); the steeper the thread, the more overhang it tests.
- ✅ **Möbius strip** — *done* (`mobius_band`): the classic one-half-twist ribbon, rastered as one continuous bead (see also `trefoil_tube`).
- ✅ **Snake-mode open cup** — *done* (`snake_soapdish`): reimplements FullControl's Snake-Mode
  Soapdish — an open corrugated wall (sine-wave footprint, lens silhouette) printed in snake mode, support-free.
- **Coaster / texture tile pack** — flat tiles with hilbert-curve, truchet, and concentric-wave fills
  — a quick way to show 2D infill patterns.
- **Parametric funnel / nozzle adapter** — two different-diameter circular ports joined by a swept
  profile (generalises `hex_adapter`).

### B. Toolpath-quality designs (exercise the optimization passes)
- ✅ **Travel-heavy / anti-stringing fixture** — *done* (`towers_grid` + `optimization_report`):
  long inter-part travels that `retract_on_travel` guards; `merge_collinear` collapses the edges.
- **Coasting/z-hop showcase** — `optimization_report` already exposes the framework; a coasting/
  z-hop-tuned variant with before/after seam stats is the next step.

### C. New library capability (design + a feature)
- ✅ **Variable-width line art** — *done* (`brush_lettering`): per-segment `ExtrusionGeometry.width`
  driven by a function, for calligraphic single-wall art.
- ✅ **Native-arc design** — *done* (`arc_vase`): a vase built from true `fc.Arc` (G2/G3) moves.
- ✅ **Extrude-in-place** — *done* (`bead_studs`): a stud/braille field via `fc.StationaryExtrusion`.
- **Multi-material / tool-change demo** — alternating regions on a toolchanger. *(needs: a richer
  tool-change story than the current `T0`/`T1` manual gcode.)*
- **Sequenced multi-object plate** — N copies with per-object purge, laid out on a grid. *(uses
  `fc.move(copy=True)`; pairs well with a future travel-reordering pass.)*
- ✅ **Conical / cylindrical non-planar mapping** — *done* (`revolve` + `textured_cone`): wrap any
  2-D `texture(around, up)` onto any `profile(height)` surface of revolution; generalises the
  hand-rolled radial maths in `nonplanar_spacer`/the vases.

### D. Backend-showcase designs
- ✅ **Print-time/material study** — *done* (`print_time_study`): one shape swept over a parameter,
  charting `simulation` output — exercises the Rust-kernel simulate fast-path on many large designs.
- ✅ **Validation gauntlet** — *done* (`validation_gauntlet`): twelve designs that each trip one
  validation rule — living documentation of the checks.

**Done so far:** `gyroid_infill`, `validation_gauntlet`, `twisted_polygon_vase`, `print_time_study`.
**Suggested next:** the **helical screw / auger** (steep-overhang test) and the **surface-conforming
transform helper** (section C — enables a whole class of conical / cylindrical-mapped designs).
