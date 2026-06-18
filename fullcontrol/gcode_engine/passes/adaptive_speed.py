"""``adaptive_speed`` - lower the feedrate on high-curvature corners (and overhangs).

A sharp direction change between two consecutive extruding moves needs a slower feedrate for the
firmware to actually reach the commanded speed and to avoid corner ringing/blobbing. For each
extruding line segment we measure the turn angle into it; the sharper the turn the more we scale
``speed`` down (between ``corner_factor`` at a 180deg hairpin and 1.0 at a straight line). If a
segment looks like an overhang (its width exceeds the layer ``height`` markedly - the same cue the
verification overhang heuristic uses), it is additionally scaled by ``overhang_factor``. Only the
``speed`` field changes; geometry and deposited material are untouched, and the result is clamped
to ``[min_speed, max_speed]``.
"""
from math import acos, hypot, pi

from fullcontrol.ir.passes import register_pass
from fullcontrol.ir.toolpath import Segment, Toolpath

_CORNER_THRESHOLD = pi / 6  # turns sharper than 30deg start scaling


def _dir(seg: Segment):
    'Unit XY direction of a segment, or None if degenerate / undefined.'
    if None in (seg.start[0], seg.start[1], seg.end[0], seg.end[1]):
        return None
    dx = seg.end[0] - seg.start[0]
    dy = seg.end[1] - seg.start[1]
    n = hypot(dx, dy)
    if n < 1e-9:
        return None
    return (dx / n, dy / n)


def _turn_angle(prev_dir, cur_dir):
    'The turn angle (rad, 0..pi) from prev_dir into cur_dir; 0 == straight ahead.'
    dot = max(-1.0, min(1.0, prev_dir[0] * cur_dir[0] + prev_dir[1] * cur_dir[1]))
    return acos(dot)


def _is_overhang(seg: Segment) -> bool:
    'Crude overhang cue: an extruding move whose width is much wider than its layer height.'
    return (seg.width is not None and seg.height is not None and seg.height > 0
            and seg.width > 2.5 * seg.height)


def adaptive_speed(toolpath: Toolpath, corner_factor: float = 0.7, overhang_factor: float = 0.5,
                   min_speed: float = 300.0, max_speed: float = 12000.0) -> Toolpath:
    '''Scale ``speed`` down on sharp-corner extruding segments (and overhangs), clamped to
    [min_speed, max_speed]. Only the speed field changes - material/geometry are unchanged.'''
    events = toolpath.events
    out = []
    prev_dir = None
    for ev in events:
        if not (isinstance(ev, Segment) and not ev.travel and ev.length and ev.length > 0):
            if isinstance(ev, Segment) and ev.travel:
                prev_dir = None  # a travel breaks corner continuity
            out.append(ev)
            continue
        cur_dir = _dir(ev)
        factor = 1.0
        if prev_dir is not None and cur_dir is not None:
            angle = _turn_angle(prev_dir, cur_dir)
            if angle > _CORNER_THRESHOLD:
                # map angle in (threshold, pi] -> factor in [1.0, corner_factor]
                t = (angle - _CORNER_THRESHOLD) / (pi - _CORNER_THRESHOLD)
                factor = 1.0 - t * (1.0 - corner_factor)
        if _is_overhang(ev):
            factor *= overhang_factor
        new_speed = ev.speed * factor if ev.speed else ev.speed
        if new_speed is not None:
            new_speed = max(min_speed, min(max_speed, new_speed))
        if new_speed != ev.speed:
            ev = Segment(ev.start, ev.end, ev.travel, new_speed, ev.length,
                         ev.deposited_volume, ev.filament_length, ev.source_index,
                         kind=ev.kind, centre=ev.centre, clockwise=ev.clockwise,
                         width=ev.width, height=ev.height, color=ev.color,
                         arc_points=ev.arc_points)
        out.append(ev)
        if cur_dir is not None:
            prev_dir = cur_dir
    return Toolpath(out)


register_pass('adaptive_speed', adaptive_speed)
