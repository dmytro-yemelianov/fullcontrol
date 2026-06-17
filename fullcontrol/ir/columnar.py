"""A columnar (numpy) view of the Toolpath IR.

The object IR (a list of `Segment` dataclasses) is the readable default. For analytic backends
that fold over *every* segment with simple arithmetic - simulation, geometric validation - a
struct-of-arrays form is faster: one numpy reduction over a contiguous column instead of a Python
loop dispatching per object.

`ColumnarToolpath.from_toolpath` flattens an object Toolpath into parallel arrays (positions are
float with NaN for an axis not yet defined; MaterialEvents, which carry material but no move, are
summed into scalars since a fold only ever totals them). The conversion is itself an O(N) Python
loop, so a *single* fold over a freshly-resolved design does not win - the speed-up is for repeated
or vectorised folds over the same arrays (and points the way to resolve() emitting columns directly).
"""
from dataclasses import dataclass

import numpy as np

from fullcontrol.core.point import Point
from fullcontrol.core.arc import Arc, arc_geometry
from fullcontrol.core.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion
from fullcontrol.core.printer import Printer
from fullcontrol.ir.toolpath import Toolpath, Segment, MaterialEvent


def _xyz(vec):
    'A (x, y, z) tuple, possibly with None components, as three floats (None -> NaN).'
    return [np.nan if c is None else c for c in vec]


@dataclass
class ColumnarToolpath:
    '''Struct-of-arrays view of a Toolpath's Segments (one row per Segment, in event order),
    plus the scalar totals of any stationary MaterialEvents.'''
    start: np.ndarray            # (N, 3) float64 - NaN where an axis is undefined
    end: np.ndarray              # (N, 3) float64
    travel: np.ndarray           # (N,) bool
    speed: np.ndarray            # (N,) float64, mm/min
    length: np.ndarray           # (N,) float64, mm
    deposited_volume: np.ndarray  # (N,) float64, mm^3
    filament_length: np.ndarray  # (N,) float64, mm
    source_index: np.ndarray     # (N,) int64
    material_volume: float       # total deposited_volume of stationary MaterialEvents
    material_filament: float     # total filament_length of stationary MaterialEvents

    @property
    def n_segments(self) -> int:
        return int(self.travel.shape[0])

    @classmethod
    def from_lists(cls, sx, sy, sz, ex, ey, ez, travel, speed, length, vol, fil, src,
                   material_volume, material_filament) -> 'ColumnarToolpath':
        'Pack per-segment column lists (built during a resolve walk) into a ColumnarToolpath.'
        start = np.column_stack([np.array(sx, dtype=np.float64), np.array(sy, dtype=np.float64),
                                 np.array(sz, dtype=np.float64)]) if sx else np.empty((0, 3))
        end = np.column_stack([np.array(ex, dtype=np.float64), np.array(ey, dtype=np.float64),
                               np.array(ez, dtype=np.float64)]) if ex else np.empty((0, 3))
        return cls(start, end, np.array(travel, dtype=bool), np.array(speed, dtype=np.float64),
                   np.array(length, dtype=np.float64), np.array(vol, dtype=np.float64),
                   np.array(fil, dtype=np.float64), np.array(src, dtype=np.int64),
                   float(material_volume), float(material_filament))

    @classmethod
    def from_toolpath(cls, toolpath: Toolpath) -> 'ColumnarToolpath':
        segs = [e for e in toolpath.events if isinstance(e, Segment)]
        material_volume = sum(e.deposited_volume for e in toolpath.events if isinstance(e, MaterialEvent))
        material_filament = sum(e.filament_length for e in toolpath.events if isinstance(e, MaterialEvent))
        n = len(segs)
        start = np.empty((n, 3), dtype=np.float64)
        end = np.empty((n, 3), dtype=np.float64)
        travel = np.empty(n, dtype=bool)
        speed = np.empty(n, dtype=np.float64)
        length = np.empty(n, dtype=np.float64)
        deposited_volume = np.empty(n, dtype=np.float64)
        filament_length = np.empty(n, dtype=np.float64)
        source_index = np.empty(n, dtype=np.int64)
        for i, s in enumerate(segs):
            start[i] = _xyz(s.start)
            end[i] = _xyz(s.end)
            travel[i] = s.travel
            speed[i] = s.speed
            length[i] = s.length
            deposited_volume[i] = s.deposited_volume
            filament_length[i] = s.filament_length
            source_index[i] = s.source_index
        return cls(start, end, travel, speed, length, deposited_volume, filament_length,
                   source_index, float(material_volume), float(material_filament))


def resolve_columnar(steps, controls, include_procedures=True, initial_extruder_on=None) -> ColumnarToolpath:
    '''A columnar resolve: the same sequential state-walk as `ir.resolve`, but writing each move's
    scalars straight into column lists instead of constructing a frozen `Segment` per move. That
    skips ~N object allocations, making it ~2x faster to resolve and feeding `simulate_columnar`
    directly for a ~2.7x faster end-to-end simulate.

    It deliberately handles only what an analytic (metrics) fold needs - moves, their resolved
    speed/length/material, and the totals of stationary extrusion. It does NOT carry arc tessellation,
    colours, pass-through ordering or optimisation passes, so it is not a drop-in for the gcode/plot
    backends; those keep the object IR. `test_columnar.py` pins this walk field-by-field to the
    canonical `resolve` so the two can never silently diverge.
    '''
    from fullcontrol.gcode.state import State
    controls.initialize()
    ctx = State(steps, controls, procedures=include_procedures)
    if initial_extruder_on is not None:
        ctx.extruder.on = initial_extruder_on
    walk = ctx.steps if include_procedures else steps

    sx, sy, sz, ex, ey, ez = [], [], [], [], [], []
    travel, speed, length, vol, fil, src = [], [], [], [], [], []
    mat_vol = mat_fil = 0.0

    for i, step in enumerate(walk):
        if isinstance(step, Arc):
            geom = arc_geometry(step, ctx.point.x, ctx.point.y, ctx.point.z)
            on = ctx.extruder.on
            spd = ctx.printer.print_speed if on else ctx.printer.travel_speed
            v = geom.arc_length * (ctx.extrusion_geometry.area or 0.0) if on else 0.0
            sx.append(ctx.point.x); sy.append(ctx.point.y); sz.append(ctx.point.z)
            ctx.point.update_from(step.end)
            ex.append(ctx.point.x); ey.append(ctx.point.y); ez.append(ctx.point.z)
            travel.append(not on); speed.append(spd); length.append(geom.arc_length)
            vol.append(v); fil.append(v * (ctx.extruder.volume_to_e or 0.0)); src.append(i)
        elif isinstance(step, Point):
            x0, y0, z0 = ctx.point.x, ctx.point.y, ctx.point.z
            dx = 0.0 if x0 is None or step.x is None else step.x - x0
            dy = 0.0 if y0 is None or step.y is None else step.y - y0
            dz = 0.0 if z0 is None or step.z is None else step.z - z0
            on = ctx.extruder.on
            ctx.point.update_from(step)
            x1, y1, z1 = ctx.point.x, ctx.point.y, ctx.point.z
            if (x1, y1, z1) != (x0, y0, z0):  # any axis changed -> a move
                ln = (dx * dx + dy * dy + dz * dz) ** 0.5
                spd = ctx.printer.print_speed if on else ctx.printer.travel_speed
                v = ln * (ctx.extrusion_geometry.area or 0.0) if on else 0.0
                sx.append(x0); sy.append(y0); sz.append(z0)
                ex.append(x1); ey.append(y1); ez.append(z1)
                travel.append(not on); speed.append(spd); length.append(ln)
                vol.append(v); fil.append(v * (ctx.extruder.volume_to_e or 0.0)); src.append(i)
        elif isinstance(step, StationaryExtrusion):
            mat_vol += step.volume
            mat_fil += step.volume * (ctx.extruder.volume_to_e or 0.0)
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

    return ColumnarToolpath.from_lists(sx, sy, sz, ex, ey, ez, travel, speed, length,
                                       vol, fil, src, mat_vol, mat_fil)
