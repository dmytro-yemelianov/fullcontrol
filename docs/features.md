# FullControl features guide

A practical, example-driven tour of the capabilities added on top of the core
`transform(steps, result_type, controls)` design model. Every snippet below is runnable as-is
(they are smoke-tested in CI via the example harness).

For *how* these fit together internally — the data-model → renderer → backend-registry
architecture — see [architecture.md](architecture.md).

```python
import fullcontrol as fc
```

A **design** is a flat list of step objects. The same list can be turned into gcode, a plot,
a simulation estimate, or a validation report by changing `result_type`.

---

## Result types (backends)

| `result_type` | returns | purpose |
|---------------|---------|---------|
| `'gcode'`     | `str`   | printer gcode |
| `'plot'`      | a plot (or `PlotData` with `raw_data=True`) | visualization |
| `'simulation'`| `SimulationResult` | time / material / flow estimate |
| `'validate'`  | `ValidationResult` | pre-flight safety checks |

```python
steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=0, z=0.2)]
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(printer_name='generic'))
```

New backends can be registered without touching `transform()` — see
`combinations/gcode_and_visualize/backends.py` and `available_backends()`.

---

## Pre-flight validation (`'validate'`)

Catch likely problems before sending gcode to a printer. Returns a `ValidationResult` with
`.ok`, `.errors`, `.warnings`, `.issues`, `.summary()` and `.raise_if_errors()`.

```python
result = fc.transform(steps, 'validate', fc.GcodeControls(
    printer_name='generic',
    initialization_data={'nozzle_temp': 210, 'build_volume_x': 200,
                         'build_volume_y': 200, 'build_volume_z': 200}))
print(result.summary())
result.raise_if_errors()   # raise if any error-level issue was found
```

Checks performed:

- **build-volume bounds** — points outside the build volume are errors; negative z is a warning
  (bounds are skipped, with an info note, if the printer defines no build volume).
- **cold extrusion** — extrusion before any hotend heating is seen.
- **temperature sanity** — hotend temp outside `[150, 350] °C`, or bed temp `> 150 °C`.
- **speed sanity** — a non-positive print/travel speed is an error (would emit an `F0` move);
  an implausibly fast feedrate (`> 60000 mm/min`) is a warning.
- **first-layer z** — the first extruding move at `z <= 0` (nozzle on/below the bed).
- **retraction balance** — filament left retracted at the end (more `Retraction` than `Unretraction`).
- **extrusion geometry** — an extruding move with a zero/undefined cross-section (no material extruded).
- **stringing** (info) — long travel moves without a preceding retraction, *only* when the design uses
  retraction elsewhere (so designs that never retract are not nagged).

---

## Retraction

Explicit, E-based retraction as first-class steps. Specify the distance in **filament mm**
(the slicer convention); a retract followed by a prime nets to zero extruded material.

```python
[fc.Retraction(),                 # printer default distance/speed
 fc.Retraction(distance=5, speed=1800),
 fc.Unretraction()]               # primes back exactly what is currently retracted
```

Defaults come from the printer config (`retraction_distance`, `retraction_speed`) and can be
overridden per step. For firmware-managed retraction instead, use
`fc.PrinterCommand(id='retract')` → `G10`.

---

## Native arc moves

`fc.Arc` emits a single `G2`/`G3` move instead of the ~100 short segments produced by the
geometry arc helpers — smaller gcode and smoother motion. It also tessellates for the plot.

```python
[fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
 fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise')]
```

- The arc starts at the current nozzle position; `centre` and `end` are absolute, and `end`
  must lie on the circle defined by the start and `centre`.
- `direction` is `'clockwise'`/`'cw'` (G2) or `'anticlockwise'`/`'ccw'` (G3).
- An optional differing `end.z` makes a helical arc; extrusion uses the true arc length.
- `segments` controls visualization density only (the gcode is always one arc command).

---

## Motion tuning

First-class steps for print-tuning parameters. Acceleration is firmware-portable; jerk and
pressure advance are firmware-specific and emitted via the gcode flavor (see below).

```python
[fc.Acceleration(printing=800, travel=1200),   # M204 P800 T1200
 fc.Jerk(x=8, y=8),                             # M205 X8 Y8        (Marlin)
 fc.PressureAdvance(value=0.05)]                # M900 K0.05        (Marlin linear advance)
```

Fields left `None` are omitted; an all-`None` object emits nothing.

---

## Gcode flavors (firmware dialects)

The firmware-specific command vocabulary (hotend/bed temperature, fan, extrusion mode,
acceleration, jerk, pressure advance) lives in a `GcodeFlavor`. Built-in flavors are
`'marlin'` (default) and `'klipper'`. Select one per design via config:

```python
fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='generic', initialization_data={'gcode_flavor': 'klipper'}))
```

Klipper accepts the standard M-codes for temperatures/fan/acceleration, but emits
`SET_PRESSURE_ADVANCE` for `PressureAdvance` and `SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY`
for `Jerk` (its nearest analogue).

Add support for another firmware by subclassing `GcodeFlavor`, overriding the methods that
differ, and registering it:

```python
from fullcontrol.gcode.flavor import GcodeFlavor, register_flavor

class Klipperish(GcodeFlavor):
    name = 'klipperish'
    def pressure_advance(self, value, tool):
        return None if value is None else f'SET_PRESSURE_ADVANCE ADVANCE={value}'

register_flavor('klipperish', Klipperish)
# now selectable: initialization_data={'gcode_flavor': 'klipperish'}
```

Inherited methods keep their Marlin behaviour, so a flavor only declares what is different.

---

## Simulation (`'simulation'`)

Estimate time, distances, material and peak flow without printing.

```python
sim = fc.transform(steps, 'simulation', fc.GcodeControls(printer_name='generic'))
print(sim.summary())   # total_time_s, extruded_volume, max_flow_rate, ...
```
