from collections import namedtuple
from math import atan2, cos, hypot, sin, tau

from fullcontrol.core.base import BaseModelPlus
from fullcontrol.core.point import Point

# default number of straight segments used to render an arc for visualization (matches the
# segment count used by the geometry arc helpers, e.g. arcXY)
ARC_VISUALIZATION_SEGMENTS = 100

_CLOCKWISE = {'clockwise', 'cw'}
_ANTICLOCKWISE = {'anticlockwise', 'anti-clockwise', 'counterclockwise', 'ccw'}
# tolerance for 'the end point lies on the circle defined by start + centre'
_RADIUS_ABS_TOL_MM = 1e-3
_RADIUS_REL_TOL = 1e-4

# resolved geometry of an arc move given its start point
ArcGeometry = namedtuple('ArcGeometry', 'clockwise cx cy radius start_angle swept dz arc_length')


def is_clockwise(direction: str) -> bool:
    'True for G2 (clockwise), False for G3 (anticlockwise); raises on an unknown direction.'
    d = (direction or '').lower()
    if d in _CLOCKWISE:
        return True
    if d in _ANTICLOCKWISE:
        return False
    raise ValueError(
        f"Arc direction must be 'clockwise'/'cw' or 'anticlockwise'/'ccw', got {direction!r}")


def arc_geometry(arc: 'Arc', sx: float, sy: float, sz: float | None = None) -> ArcGeometry:
    '''Resolve an arc's geometry from its start position (sx, sy, sz).

    Validates that the end point lies on the circle defined by the start and centre, then
    returns the swept angle (always positive, 0 -> a full revolution), the z change and the
    true (possibly helical) arc length.
    '''
    if sx is None or sy is None:
        raise ValueError('Arc has no start position - a Point defining the current x/y must precede the Arc')
    clockwise = is_clockwise(arc.direction)
    cx, cy = arc.centre.x, arc.centre.y
    ex, ey = arc.end.x, arc.end.y
    radius = hypot(sx - cx, sy - cy)
    if abs(hypot(ex - cx, ey - cy) - radius) > _RADIUS_ABS_TOL_MM + _RADIUS_REL_TOL * radius:
        raise ValueError(
            f'Arc end point ({ex}, {ey}) is not on the arc circle '
            f'(radius from start {radius:.4f} != radius from end {hypot(ex - cx, ey - cy):.4f}); '
            'check centre/end')
    start_angle = atan2(sy - cy, sx - cx)
    end_angle = atan2(ey - cy, ex - cx)
    swept = (start_angle - end_angle) % tau if clockwise else (end_angle - start_angle) % tau
    if swept == 0:  # coincident start/end -> a full revolution
        swept = tau
    dz = arc.end.z - sz if (arc.end.z is not None and sz is not None) else 0
    return ArcGeometry(clockwise, cx, cy, radius, start_angle, swept, dz, hypot(radius * swept, dz))


def arc_points(arc: 'Arc', sx: float, sy: float, sz: float | None, geom: ArcGeometry) -> list:
    '''Tessellate the arc into `arc.segments` (x, y, z) points after the start point.

    The final point is snapped to the exact end coordinates to avoid float drift. Used for
    visualization and for computing an arc's contribution to the bounding box / point count.
    '''
    sign = -1 if geom.clockwise else 1
    points = []
    for i in range(1, arc.segments + 1):
        if i == arc.segments:
            px, py = arc.end.x, arc.end.y
            pz = arc.end.z if arc.end.z is not None else sz
        else:
            frac = i / arc.segments
            angle = geom.start_angle + sign * geom.swept * frac
            px = geom.cx + geom.radius * cos(angle)
            py = geom.cy + geom.radius * sin(angle)
            pz = sz + geom.dz * frac if sz is not None else arc.end.z
        points.append((px, py, pz))
    return points


class Arc(BaseModelPlus):
    '''A circular (or helical) arc move from the current point, around `centre`, to `end`.

    Emits a single G2 (clockwise) / G3 (anticlockwise) gcode move instead of the many short
    line segments produced by the geometry arc helpers. The start of the arc is the current
    nozzle position; `centre` and `end` are absolute positions, and `end` must lie on the
    circle defined by the start point and `centre` (validated by arc_geometry).

    Attributes:
        centre (Point): centre of the arc - x and y required (z is ignored; arcs sweep in the XY plane).
        end (Point): end position - x and y required; an optional differing z makes a helical arc.
        direction (str): 'clockwise'/'cw' (G2) or 'anticlockwise'/'ccw' (G3).
        segments (int): number of straight segments used to render the arc for visualization.
    '''
    centre: Point | None = None
    end: Point | None = None
    direction: str = 'clockwise'
    segments: int = ARC_VISUALIZATION_SEGMENTS
