"""The Toolpath IR and the single `resolve` pass.

A FullControl design is a list of step objects whose meaning depends on the running state
(None fields inherit, extrusion volume accumulates, etc.). Historically each backend re-walked
that list and re-implemented this forward state propagation. `resolve(design) -> Toolpath`
does it **once**, producing an immutable, backend-agnostic intermediate representation: a
stream of fully-resolved events - mostly `Segment`s, where every move already carries absolute
coordinates, the resolved feedrate, and the *semantic* material deposited.

Backends then consume the IR as plain folds (no state machine of their own). The simulation
backend is the first consumer (see fullcontrol/simulate/run.py); the IR is designed to grow -
each `Segment` already carries enough for a gcode dialect (arc centre/direction for I/J and
G2/G3) so further backends can migrate onto it incrementally.
"""
from dataclasses import dataclass, field

from fullcontrol.core.point import Point
from fullcontrol.core.arc import Arc, arc_geometry
from fullcontrol.core.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion
from fullcontrol.core.printer import Printer

Vec3 = tuple  # (x, y, z) absolute; a component may be None before it is first defined


@dataclass(frozen=True)
class Segment:
    '''A resolved move from `start` to `end` (absolute). `length` is the true path length
    (arc length for arcs; 0 for a first positioning move). `deposited_volume`/`filament_length`
    are the semantic material for this move - a FFF target maps them to E, a laser/CNC target
    would instead use them as power/feed.'''
    start: Vec3
    end: Vec3
    travel: bool               # True when not extruding
    speed: float               # mm/min
    length: float              # mm
    deposited_volume: float    # mm^3
    filament_length: float     # mm of feedstock
    source_index: int          # provenance: the resolved-step index that produced this
    kind: str = 'line'         # 'line' | 'arc'
    centre: tuple = None       # (cx, cy) for arcs - lets a gcode dialect emit I/J
    clockwise: bool = False    # arcs: G2 (clockwise) vs G3
    width: float = None        # extrusion cross-section in effect for this move (for plot / validate)
    height: float = None


@dataclass(frozen=True)
class MaterialEvent:
    'Stationary material change (e.g. StationaryExtrusion) - material but no XYZ move.'
    deposited_volume: float
    filament_length: float
    source_index: int


@dataclass
class Toolpath:
    'The resolved intermediate representation: an ordered event stream.'
    events: list = field(default_factory=list)


def _distance(p1, p2) -> float:
    'Euclidean distance, ignoring any axis not defined in both points.'
    dx = 0.0 if p1.x is None or p2.x is None else p2.x - p1.x
    dy = 0.0 if p1.y is None or p2.y is None else p2.y - p1.y
    dz = 0.0 if p1.z is None or p2.z is None else p2.z - p1.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def resolve(steps, controls) -> Toolpath:
    '''The single state-propagation pass: design -> Toolpath IR.

    Reuses the gcode `State` for *initialisation* only (printer-config resolution, the primer,
    and the start/end procedures, plus the initial extruder/printer/geometry context), then
    does one forward walk that emits backend-agnostic IR events.
    '''
    from fullcontrol.gcode.state import State
    controls.initialize()
    ctx = State(steps, controls)   # config + procedures + the single running context
    events = []

    for i, step in enumerate(ctx.steps):
        if isinstance(step, Arc):
            geom = arc_geometry(step, ctx.point.x, ctx.point.y, ctx.point.z)
            on = ctx.extruder.on
            speed = ctx.printer.print_speed if on else ctx.printer.travel_speed
            vol = geom.arc_length * (ctx.extrusion_geometry.area or 0.0) if on else 0.0
            start = (ctx.point.x, ctx.point.y, ctx.point.z)
            ctx.point.update_from(step.end)
            end = (ctx.point.x, ctx.point.y, ctx.point.z)
            events.append(Segment(start, end, not on, speed, geom.arc_length, vol,
                                  vol * (ctx.extruder.volume_to_e or 0.0), i, kind='arc',
                                  centre=(geom.cx, geom.cy), clockwise=geom.clockwise,
                                  width=ctx.extrusion_geometry.width, height=ctx.extrusion_geometry.height))
        elif isinstance(step, Point):
            length = _distance(ctx.point, step)
            start = (ctx.point.x, ctx.point.y, ctx.point.z)
            on = ctx.extruder.on
            ctx.point.update_from(step)
            end = (ctx.point.x, ctx.point.y, ctx.point.z)
            if end != start:  # any axis changed -> a move (length may be 0 for first positioning)
                speed = ctx.printer.print_speed if on else ctx.printer.travel_speed
                vol = length * (ctx.extrusion_geometry.area or 0.0) if on else 0.0
                events.append(Segment(start, end, not on, speed, length, vol,
                                      vol * (ctx.extruder.volume_to_e or 0.0), i,
                                      width=ctx.extrusion_geometry.width, height=ctx.extrusion_geometry.height))
        elif isinstance(step, Extruder):
            ctx.extruder.update_from(step)
            if getattr(step, 'units', None) is not None or getattr(step, 'dia_feed', None) is not None:
                ctx.extruder.update_e_ratio()
        elif isinstance(step, ExtrusionGeometry):
            ctx.extrusion_geometry.update_from(step)
            try:
                ctx.extrusion_geometry.update_area()
            except TypeError:
                pass  # not all parameters set yet (None arithmetic)
        elif isinstance(step, Printer):
            ctx.printer.update_from(step)
        elif isinstance(step, StationaryExtrusion):
            events.append(MaterialEvent(step.volume, step.volume * (ctx.extruder.volume_to_e or 0.0), i))
        # steps with no effect on time/material (temps, fan, commands, raw gcode, retraction)
        # are skipped here - a future gcode/plot consumer would model them as further IR events
    return Toolpath(events)
