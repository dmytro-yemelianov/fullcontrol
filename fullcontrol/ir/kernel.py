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
from fullcontrol.core.arc import Arc
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
    '''Walk the resolved step list, replaying the non-motion state updates exactly as the
    Python resolve does, and emit the (tag, a, b, c) primitive rows. Returns None if any step is
    an Arc (signal to fall back to Python); unrecognised non-motion steps are skipped as no-ops,
    matching the Python reference walk.

    A scratch copy of the extruder / extrusion_geometry is mutated here purely to resolve the
    per-step volume_to_e and area/width/height that the kernel needs; the caller's ctx is left
    untouched (we deep-copy first).
    '''
    extruder = deepcopy(ctx.extruder)
    geom = deepcopy(ctx.extrusion_geometry)

    tags, av, bv, cv = [], [], [], []
    for step in walk:
        if isinstance(step, Arc):
            return None  # arcs are out of scope for this skeleton -> fall back
        if isinstance(step, Point):
            tags.append(0)
            av.append(_f(step.x))
            bv.append(_f(step.y))
            cv.append(_f(step.z))
        elif isinstance(step, StationaryExtrusion):
            tags.append(4)
            av.append(float(step.volume))
            bv.append(nan)
            cv.append(nan)
        elif isinstance(step, Extruder):
            # mirror the resolve walk: update_from, then recompute e-ratio if units/dia_feed set
            extruder.update_from(step)
            if getattr(step, 'units', None) is not None or getattr(step, 'dia_feed', None) is not None:
                extruder.update_e_ratio()
            on = step.on
            tags.append(1)
            av.append(-1.0 if on is None else (1.0 if on else 0.0))
            bv.append(_f(extruder.volume_to_e))
            cv.append(nan)
        elif isinstance(step, ExtrusionGeometry):
            geom.update_from(step)
            try:
                geom.update_area()
            except TypeError:
                pass  # not all parameters set yet (None arithmetic) - area stays as-is
            tags.append(2)
            av.append(_f(geom.area))
            bv.append(_f(geom.width))
            cv.append(_f(geom.height))
        elif isinstance(step, Printer):
            tags.append(3)
            av.append(_f(step.print_speed))
            bv.append(_f(step.travel_speed))
            cv.append(nan)
        else:
            # any other step type (e.g. ManualGcode / PrinterCommand injected by the primer and
            # start/end procedures) is a no-op in resolve_columnar's walk. We still emit a row
            # (tag -1) so the kernel's per-step index stays aligned with the Python enumerate()
            # index, which is what becomes a move's source_index. Only an Arc forces a fall-back.
            tags.append(-1)
            av.append(nan)
            bv.append(nan)
            cv.append(nan)
    return tags, av, bv, cv


def resolve_columnar_rust(steps, controls, include_procedures=True, initial_extruder_on=None,
                          state=None):
    '''Rust-backed columnar resolve. Returns a `ColumnarToolpath` identical to the Python
    `resolve_columnar`, or None if the extension is unavailable or the design contains a step
    the kernel does not model (Arc / unknown) - in which case the caller should fall back.
    '''
    if _kernel is None:
        return None

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
    walk = ctx.steps if include_procedures else steps

    flat = _flatten(walk, ctx)
    if flat is None:
        return None
    tags, av, bv, cv = flat

    on = ctx.extruder.on
    init_on = -1.0 if on is None else (1.0 if on else 0.0)

    (start, end, travel, speed, length, vol, fil, src, wid, hgt,
     material_volume, material_filament) = _kernel.resolve_columnar(
        tags, av, bv, cv,
        init_on,
        _f(ctx.extruder.volume_to_e),
        _f(ctx.printer.print_speed),
        _f(ctx.printer.travel_speed),
        _f(ctx.extrusion_geometry.area),
        _f(ctx.extrusion_geometry.width),
        _f(ctx.extrusion_geometry.height),
        _f(ctx.point.x),
        _f(ctx.point.y),
        _f(ctx.point.z),
    )

    return ColumnarToolpath(start, end, travel, speed, length, vol, fil, src,
                            float(material_volume), float(material_filament), wid, hgt)
