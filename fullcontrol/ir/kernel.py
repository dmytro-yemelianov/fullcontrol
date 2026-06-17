"""Rust-backed columnar resolve (microkernel proof-of-concept).

The columnar IR (struct-of-arrays) is the ABI boundary. This wrapper builds the gcode `State`
exactly as `fullcontrol.ir.columnar.resolve_columnar` does, then FLATTENS the resolved step list
into primitive arrays a Rust kernel can fold over without ever touching pydantic. The kernel
re-implements the sequential state-walk for the common LINEAR step set and returns the same numpy
columns; this wrapper packs them into a drop-in `ColumnarToolpath`.

If the design (after primer/procedure resolution) contains an `Arc`, `resolve_columnar_rust`
returns None - the signal for the caller to fall back to the pure-Python `resolve_columnar`.
Other non-motion step types injected by the primer/procedures (e.g. ManualGcode) are no-ops in
the columnar walk and are simply skipped, exactly as the Python reference does.

Flatten ABI (per resolved step -> a (tag, a, b, c) row):
  0 Point:               a=x  b=y  c=z      (NaN component => inherit previous)
  1 Extruder:            a=on (-1 none / 0 off / 1 on)  b=volume_to_e (NaN => no change)
  2 ExtrusionGeometry:   a=area (NaN => None)  b=width (NaN => undefined)  c=height
  3 Printer:             a=print_speed (NaN => no change)  b=travel_speed (NaN => no change)
  4 StationaryExtrusion: a=volume
The per-step extruder volume_to_e and the geometry area/width/height are resolved on the Python
side (replaying the exact update logic) so the kernel stays a pure arithmetic fold.
"""
from copy import deepcopy
from math import nan

from fullcontrol.core.point import Point
from fullcontrol.core.arc import Arc, arc_geometry
from fullcontrol.core.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion
from fullcontrol.core.printer import Printer
from fullcontrol.ir.columnar import ColumnarToolpath

try:  # the compiled extension is optional - absence just disables the fast path
    import fullcontrol_kernel as _kernel
except ImportError:  # pragma: no cover - exercised by the importorskip in the test
    _kernel = None


def kernel_available() -> bool:
    'True if the compiled Rust extension is importable.'
    return _kernel is not None


def _f(v):
    'A scalar with None -> NaN.'
    return nan if v is None else float(v)


def _flatten(walk, ctx):
    '''Walk the resolved step list, replaying the non-motion state updates exactly as the Python
    resolve does, and emit the (tag, a, b, c, d) primitive rows the kernel folds over.

    Arcs are supported by pre-resolving them here with the tested `arc_geometry`: a running point
    (px, py, pz) is tracked so the arc's start is known, the arc length is computed, and the row
    carries the *absolute* resolved end (a, b, c) and arc length (d) - the kernel then treats it as
    a plain move. Unrecognised non-motion steps (e.g. ManualGcode from the primer) are emitted as
    no-op rows (tag -1) so the per-step index stays aligned with source_index.

    Scratch copies of extruder / extrusion_geometry are mutated here only to resolve the per-step
    volume_to_e and area/width/height the kernel needs; the caller's ctx is left untouched.
    '''
    extruder = deepcopy(ctx.extruder)
    geom = deepcopy(ctx.extrusion_geometry)
    px, py, pz = ctx.point.x, ctx.point.y, ctx.point.z  # running point, for arc start

    tags, av, bv, cv, dv = [], [], [], [], []
    # bind the column append methods to locals (the hot loop runs once per resolved step) and
    # check the dominant `Point` type first
    ta, aa, ba, ca, da = tags.append, av.append, bv.append, cv.append, dv.append
    for step in walk:
        if isinstance(step, Point):
            x, y, z = step.x, step.y, step.z
            if x is not None:
                px = x
            if y is not None:
                py = y
            if z is not None:
                pz = z
            ta(0)
            aa(nan if x is None else x)  # None -> NaN inline (avoids a call per coordinate)
            ba(nan if y is None else y)
            ca(nan if z is None else z)
            da(0.0)
        elif isinstance(step, Arc):
            g = arc_geometry(step, px, py, pz)
            end = step.end
            px = px if end.x is None else end.x
            py = py if end.y is None else end.y
            pz = pz if end.z is None else end.z
            ta(5)
            aa(_f(px)); ba(_f(py)); ca(_f(pz)); da(float(g.arc_length))
        elif isinstance(step, Extruder):
            # mirror the resolve walk: update_from, then recompute e-ratio if units/dia_feed set
            extruder.update_from(step)
            if getattr(step, 'units', None) is not None or getattr(step, 'dia_feed', None) is not None:
                extruder.update_e_ratio()
            on = step.on
            ta(1)
            aa(-1.0 if on is None else (1.0 if on else 0.0))
            ba(_f(extruder.volume_to_e)); ca(nan); da(0.0)
        elif isinstance(step, ExtrusionGeometry):
            geom.update_from(step)
            try:
                geom.update_area()
            except TypeError:
                pass  # not all parameters set yet (None arithmetic) - area stays as-is
            ta(2)
            aa(_f(geom.area)); ba(_f(geom.width)); ca(_f(geom.height)); da(0.0)
        elif isinstance(step, StationaryExtrusion):
            ta(4)
            aa(float(step.volume)); ba(nan); ca(nan); da(0.0)
        elif isinstance(step, Printer):
            ta(3)
            aa(_f(step.print_speed)); ba(_f(step.travel_speed)); ca(nan); da(0.0)
        else:
            ta(-1)
            aa(nan); ba(nan); ca(nan); da(0.0)
    return tags, av, bv, cv, dv


def _build_ctx(steps, controls, include_procedures, initial_extruder_on, state):
    'Build (or reuse) the gcode State context, exactly as resolve_columnar does.'
    from fullcontrol.gcode.state import State
    controls.initialize()
    if state is None:
        ctx = State(steps, controls, procedures=include_procedures)
    else:
        from types import SimpleNamespace
        ctx = SimpleNamespace(point=deepcopy(state.point), extruder=deepcopy(state.extruder),
                              printer=deepcopy(state.printer),
                              extrusion_geometry=deepcopy(state.extrusion_geometry), steps=state.steps)
    if initial_extruder_on is not None:
        ctx.extruder.on = initial_extruder_on
    return ctx


def _init_args(ctx):
    '''The ten initial running-context scalars the kernel needs (mirrors the gcode State after
    init); passed as one list. Order must match walk.rs `Ctx::from_scalars`.'''
    on = ctx.extruder.on
    return [
        -1.0 if on is None else (1.0 if on else 0.0),
        _f(ctx.extruder.volume_to_e),
        _f(ctx.printer.print_speed),
        _f(ctx.printer.travel_speed),
        _f(ctx.extrusion_geometry.area),
        _f(ctx.extrusion_geometry.width),
        _f(ctx.extrusion_geometry.height),
        _f(ctx.point.x), _f(ctx.point.y), _f(ctx.point.z),
    ]


def resolve_columnar_rust(steps, controls, include_procedures=True, initial_extruder_on=None,
                          state=None):
    '''Rust-backed columnar resolve. Returns a `ColumnarToolpath` identical to the Python
    `resolve_columnar`, or None if the extension is unavailable - in which case the caller should
    fall back. Arcs are supported (pre-resolved in `_flatten`).
    '''
    if _kernel is None:
        return None
    ctx = _build_ctx(steps, controls, include_procedures, initial_extruder_on, state)
    walk = ctx.steps if include_procedures else steps
    tags, av, bv, cv, dv = _flatten(walk, ctx)

    (start, end, travel, speed, length, vol, fil, src, wid, hgt,
     material_volume, material_filament) = _kernel.resolve_columnar(
        tags, (av, bv, cv, dv), _init_args(ctx))

    return ColumnarToolpath(start, end, travel, speed, length, vol, fil, src,
                            float(material_volume), float(material_filament), wid, hgt)


def emit_gcode_moves_rust(toolpath, relative_e=True, travel_g1_e0=False):
    '''Rust-backed g-code motion emission: serialize the Toolpath IR and let the Rust engine emit
    the G0/G1/G2/G3 + stationary-extrusion lines (byte-identical to the Python dialect's motion
    lines). Returns a list of lines, or None if the extension is unavailable.

    This covers motion only - the start/end procedures, retraction/temperature/fan commands and the
    extrusion-mode line stay in Python for now (see rust_kernel/src/gcode.rs).
    '''
    if _kernel is None:
        return None
    from fullcontrol.ir.serialize import to_json
    return list(_kernel.emit_gcode_moves(to_json(toolpath), relative_e, travel_g1_e0))


def emit_gcode_rust(toolpath, relative_e=True, travel_g1_e0=False):
    '''Rust-backed FULL g-code emission: serialize the Toolpath IR (resolved *with* procedures) and
    let the Rust engine emit the complete line list - motion plus the common non-motion commands
    (extrusion mode, hotend/bed temperature, fan, ManualGcode) - byte-identical to the Python
    gcode for designs within scope. Join with '\\n' for the file. None if the extension is absent.

    Not yet emitted (still Python): retraction, acceleration/jerk/pressure-advance, PrinterCommand
    command-lists, GcodeComment line-append, non-Marlin flavours.
    '''
    if _kernel is None:
        return None
    from fullcontrol.ir.serialize import to_json
    return list(_kernel.emit_gcode(to_json(toolpath), relative_e, travel_g1_e0))


def simulate_rust(steps, controls, include_procedures=True, initial_extruder_on=None, state=None):
    '''Rust-backed simulation: one Rust pass walks the design and folds it straight into the nine
    SimulationResult metrics (no per-move arrays cross back to Python). Returns a SimulationResult,
    or None if the extension is unavailable so the caller can fall back to `simulate_columnar`.
    '''
    if _kernel is None:
        return None
    from fullcontrol.simulate.result import SimulationResult
    ctx = _build_ctx(steps, controls, include_procedures, initial_extruder_on, state)
    walk = ctx.steps if include_procedures else steps
    tags, av, bv, cv, dv = _flatten(walk, ctx)

    (total_time_s, print_time_s, travel_time_s, extruding_distance, travel_distance,
     extruded_volume, filament_length, segment_count, max_flow_rate) = _kernel.simulate(
        tags, (av, bv, cv, dv), _init_args(ctx))

    return SimulationResult(
        total_time_s=total_time_s, print_time_s=print_time_s, travel_time_s=travel_time_s,
        extruding_distance=extruding_distance, travel_distance=travel_distance,
        extruded_volume=extruded_volume, filament_length=filament_length,
        segment_count=int(segment_count), max_flow_rate=max_flow_rate)
