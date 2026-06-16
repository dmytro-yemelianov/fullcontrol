# FullControl architecture

This document explains how a FullControl *design* becomes gcode or a plot, and the two
clean seams for extending the library. It reflects the post-refactor structure (data
classes + dispatch renderers + an open backend registry).

## The big picture

A **design is a plain Python list of "steps"** — data objects describing a stream of
state changes:

```python
import fullcontrol as fc
steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)]
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(printer_name='ender_3'))
```

The same list can be turned into different outputs:

```
                         ┌────────────────────────── backend registry ──────────────────────────┐
 design (list[step]) ──▶ transform(steps, result_type, controls) ──▶ run the matching backend ──▶ result
                         │   'gcode'      → gcode driver  + render_gcode                         │
                         │   'plot'       → visualize driver + render_visualize                  │
                         │   'simulation' → simulate (time/material/flow estimate)               │
                         │   'validate'   → pre-flight checks (bounds, cold extrusion, ...)       │
                         │   '<your backend>' → register_backend(...)                            │
                         └───────────────────────────────────────────────────────────────────────┘
```

Key idea: **the step classes are data; they do not contain output logic.** Each backend
walks the step list with its own running `State` and asks a *renderer* what to emit for
each step. This keeps the classes simple and lets new backends consume the exact same
designs.

## The data model

- **`BaseModelPlus`** (`fullcontrol/base.py`) — a pydantic v2 base adding dict-style
  access (`step['x']`), `update_from(other)` (copy non-None fields), and a validator
  that rejects unknown construction fields with a helpful message.
- **Step classes** — `Point` (x, y, z, color), `Arc` (native G2/G3 curved move) plus
  *state* / *action* objects (`Extruder`, `Printer`, `ExtrusionGeometry`, `Fan`, `Hotend`,
  `Buildplate`, `StationaryExtrusion`, `Retraction`, `Unretraction`, `Acceleration`,
  `ManualGcode`, `PrinterCommand`, `GcodeComment`, `PlotAnnotation`).
- **State propagation** — fields left as `None` inherit the most recent value; a backend
  keeps a running tracking instance (`state.point`, `state.extruder`, ...) updated via
  `update_from`. So a `Point(x=10)` after `Point(x=0, y=0, z=0)` only changes x.
- **Controls** — `GcodeControls` / `PlotControls` configure a run (printer, style, ...);
  they are config, not steps.

The user-facing classes are assembled in
`fullcontrol/combinations/gcode_and_visualize/classes.py`: dual-backend concepts inherit
both backend subclasses (`class Point(gc.Point, vis.Point)`); single-backend concepts
re-expose one. A drift-guard test (`tests/unit/test_architecture.py`) fails if a backend
class is added without being exposed here or without a renderer.

## Backends: state + driver + renderer

Each backend is three small pieces:

| piece | gcode | plot |
|-------|-------|------|
| **State** (running context) | `gcode/state.py` | `visualize/state.py` |
| **driver** (the loop) | `gcode/steps2gcode.py` | `visualize/steps2visualization.py` |
| **renderer** (per-step output) | `gcode/renderers.py` | `visualize/renderers.py` |

The driver builds the `State`, then loops the steps and dispatches each through the
renderer:

```python
for step in state.steps:
    line = render_gcode(step, state)   # singledispatch on type(step)
    if line is not None:
        state.gcode.append(line)
```

A **renderer** is a `functools.singledispatch` function with one handler per step type.
A step with no representation for that backend falls through to the default (does
nothing). Because dispatch is by type via the MRO, the combined user classes and the
multiaxis subclasses both resolve to the right handler.

## Extension point 1 — a new step type

1. Add the data class in the relevant backend subpackage (and expose it in `classes.py`).
2. Register a handler in that backend's renderer:

```python
@render_gcode.register
def _(step: MyStep, state):
    return f'... gcode for {step} ...'
```

The drift-guard test enforces that every backend step class has a renderer.

## Extension point 2 — a new backend

A backend is "register a runner for a `result_type`". Minimal example — a backend that
returns the number of extruding points:

```python
from fullcontrol.combinations.gcode_and_visualize.backends import register_backend
from fullcontrol.combinations.gcode_and_visualize.classes import PlotControls

def _run_point_count(steps, controls, show_tips):
    return sum(1 for s in steps if type(s).__name__ == 'Point')

register_backend('point_count', PlotControls, _run_point_count)

# now usable with no change to transform():
fc.transform(steps, 'point_count')
```

For a real backend you would typically add a `State`, a driver loop, and a renderer
(mirroring the gcode/plot trio), then register its runner. `available_backends()` lists
what is registered; an unknown `result_type` raises a clear error.

The experimental multiaxis (4/5-axis) and `lab/` `control_code`/`3d_model`/laser outputs
follow this same shape (their own State + renderer registrations), which is why they
reuse the shared step classes.

## File map

```
fullcontrol/
  core/                         backend-free foundation: BaseModelPlus (base.py),
                                generic data classes (point/printer/*_classes/aux),
                                utilities (check, extra_functions), common aggregator.
                                Must not import gcode/visualize (enforced by
                                tests/unit/test_core_boundary.py). The old top-level
                                module paths (fullcontrol/base.py, point.py, ...) are
                                thin re-export shims for compatibility.
  geometry/                     pure path generators -> list[Point]
  gcode/                        gcode backend: state, steps2gcode (driver),
                                renderers (singledispatch), number_format, devices import
  visualize/                    plot backend: state, steps2visualization (driver),
                                renderers, plotly, tube_mesh, mesh_export (STL)
  devices/                      printer profiles (singletool python, cura/community json)
  combinations/.../classes.py   user-facing combined classes
  combinations/.../backends.py  the result_type -> backend registry
  combinations/.../common.py    transform()
lab/                            experimental: multiaxis, bezier/convex/intersect, formats
tests/unit/                     fast unit suite (incl. architecture drift-guard)
```

## Invariants worth keeping

- Step classes stay data + small emission helpers; output logic lives in renderers.
- Refactors keep gcode/plot output byte-identical (capture a baseline, diff after).
- `tests/unit/test_architecture.py` guards the class/renderer coupling.
- ruff enforces modern style (is-None, PEP 604 unions, pyupgrade); CI runs the unit
  suite on Python 3.10–3.13.
