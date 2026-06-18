# New design proposals — eye-catching demos grounded in FullControl features

These are candidate gallery designs that go *beyond* the current set (cosine/lobed vases, ripple/wave
modulation, non-planar washers & bowls, gyroid, twisted/morphing polygons, helical screws,
revolve-wrapped cones, Möbius, trefoil tube, travel-grid, snake-mode soapdish). They deliberately lean
on what only FullControl (algorithmic, continuous-bead, non-planar, arc-native, variable-width) can do.

The three features the current gallery never exercises — and which would each anchor a new *capability*
demo — are **native `fc.Arc`**, **per-segment variable `ExtrusionGeometry.width`**, and
**`fc.StationaryExtrusion`** (extrude-in-place), plus the **five-axis** lab. Lead with those.

## Obvious — natural crowd-pleasers

| # | name | concept | features | knobs | difficulty |
|---|------|---------|----------|-------|------------|
| 1 | `lattice_vase` | double-wall vase whose wall is a periodic diamond/Voronoi lattice (radius jumps in/out on a tiling) — a self-bridging open "wireframe" vessel | revolve-style spiral, thresholded texture, opt. retraction at row breaks | cells_around, cells_up, wall_gap, radius, height, taper | medium |
| 2 | `twisted_lampshade` | tall flaring shade with vertical ribs that twist with height; thin wall for translucent moiré | vase spiral, height-driven rotation + flare | ribs, twist_turns, flare, rib_depth, height | easy |
| 3 | `spirograph_coaster` | flat single-layer disc whose path is a hypotrochoid (spirograph/guilloché) laid as one bead | single planar layer, ExtrusionGeometry, pairs with variable width | R, r, d, loops, disc_radius, line_width | easy |
| 4 | `carafe` | surface-of-revolution vessel with a freeform Bézier/superellipse silhouette — "design your own bottle" | revolve with custom profile from control points, opt. texture | profile_points, height, neck_radius, belly_radius | easy |
| 5 | `honeycomb_planter` | cylinder/cone with a true hexagonal honeycomb wall: open windows bordered by raised ribs | revolve thresholded hex texture, opt. extruder micro-hops | cells_around, rows, rib_width, window_depth, taper | medium |
| 6 | `nesting_bowls` | N concentric bowls on one plate, sequenced with extruder-off travels — a practical multi-object plate built to exercise the optimisation passes | move(copy=True), Extruder on/off, retract_on_travel, z_hop | count, base_radius, radius_step, height, wall | medium |

## Non-obvious — exploiting features in surprising ways

| # | name | concept | features | difficulty |
|---|------|---------|----------|------------|
| 7 | `arc_vase` | vase whose every layer is a closed loop of true `fc.Arc` (G2/G3) moves with helical end-z — a handful of arc commands per layer instead of hundreds of segments; glass-smooth, tiny g-code, **impossible as line segments** at the same fidelity | native `fc.Arc` (helical end-z), ExtrusionGeometry | medium |
| 8 | `arc_box` | rounded-rectangle prism with genuine arc-fillet corners and straight sides, climbing as one spiral — line+arc interleaved in one vase | `fc.Point` sides + `fc.Arc` corners | medium |
| 9 | `brush_lettering` | flat plaque where a bead traces a stroke whose **width swells and thins** like a brush (fat downstrokes, hairline upstrokes) via a fresh `ExtrusionGeometry` per segment — true calligraphic line weight no slicer can do | **per-segment variable width** | medium |
| 10 | `overhang_dragon` | diagonal cantilever/spire that climbs steeply by shifting each layer's centre while narrowing the bead — an aggressive overhang stunt that self-supports via bridging | non-planar centre shift, per-segment width | hard |
| 11 | `halftone_disc` | flat disc whose **bead width is modulated by a grayscale image** sampled in polar coords (dark→fat, light→hairline), or binary QR via `Extruder` on/off — the print *is* a halftone; the data lives in the toolpath | per-segment width from image, or Extruder on/off | medium/hard |
| 12 | `function_relief` | non-planar raster tile whose surface height is an arbitrary `z = f(x,y)` (interference, Gaussian, heightmap), z varying *within* each pass — a printable 3-D plot | non-planar z-within-path, boustrophedon | medium |
| 13 | `waveform_ring` | bangle/ring whose top edge is an audio waveform wrapped around the circumference — amplitude drives wall height per angle, so a recorded message becomes wearable | vase spiral with per-angle height from a sampled array | easy/medium |
| 14 | `bead_studs` | flat plate dotted with deliberate domes built by `fc.StationaryExtrusion` (nozzle parks and oozes a set volume) — laid out as braille, a stud grid, or upholstery nail-heads | **`StationaryExtrusion`**, Extruder on/off, z_hop | medium |
| 15 | `facet_sphere` | faceted dome over-tessellated into collinear sub-segments so that `merge_collinear` is *what makes it printable* — a design that is a vehicle for the optimiser; a vivid sequel to `towers_grid` | dense collinear subdivision + merge_collinear/coasting, optimization_report | easy/medium |
| 16 | `fiveaxis_elbow` | curved-wall cup / pipe elbow where the build direction tilts (B/C) to keep the nozzle normal to a curving surface — beads laid *along* a doubly-curved wall, impossible on 3 axes | `lab.fullcontrol.fiveaxis` XYZBC points | hard |

## Suggested lead set

- **Capability-expanding flagships** (each demonstrates a feature the gallery never shows):
  `arc_vase` (#7, native arcs), `brush_lettering` (#9, variable width), `bead_studs` (#14,
  StationaryExtrusion), `fiveaxis_elbow` (#16, five-axis).
- **Quick high-ROI visuals:** `spirograph_coaster` (#3), `waveform_ring` (#13), `twisted_lampshade` (#2).
- **"Only FullControl" statements:** `halftone_disc` (#11), `function_relief` (#12).
- **Optimiser storytelling:** `facet_sphere` (#15), `nesting_bowls` (#6).

Key reference files for implementing these: `examples/textured_cone.py` + `revolve` (for #1/#4/#5),
`examples/snake_soapdish.py` (boustrophedon idiom for #12), `examples/nonplanar_spacer.py`
(z-within-path for #10/#12), `examples/towers_grid.py` + `optimization_report` (for #6/#15),
`fullcontrol/core/arc.py` (Arc/helical-arc for #7/#8), the `ExtrusionGeometry`/`StationaryExtrusion`
classes (for #9/#11/#14), and `lab/fullcontrol/fiveaxis.py` (for #16).
