"""``arc_fit`` - collapse a run of short straight extruding moves that lie on a common circle
into a single ``kind='arc'`` Segment (which re-emits as a G2/G3 move).

A sliding window of >=3 consecutive *extruding line* segments is grown while every vertex stays
on a common circle within ``tolerance`` (mm). When the window closes, its points are replaced by
one arc Segment whose ``deposited_volume``/``filament_length`` are the exact sums of the merged
segments (material is conserved bit-for-bit), and whose ``length`` is the true arc length. Tight
(radius < 0.5 mm) or short (total chord < 1 mm) curves are left as lines - small fillets are
better as lines than as a wobbly G2/G3.
"""
from math import atan2, cos, hypot, sin, tau

from fullcontrol.ir.passes import register_pass
from fullcontrol.ir.toolpath import Segment, Toolpath

_MIN_RADIUS = 0.5   # mm - tighter curves stay as lines
_MIN_CHORD = 1.0    # mm - shorter runs stay as lines
_MIN_SEGMENTS = 3   # need at least 3 consecutive lines (>=4 points) to define an arc reliably


def _is_fittable(seg: Segment) -> bool:
    'A planar (constant-Z) extruding straight move with fully-defined XY endpoints.'
    return (isinstance(seg, Segment) and seg.kind == 'line' and not seg.travel
            and seg.start[0] is not None and seg.start[1] is not None
            and seg.end[0] is not None and seg.end[1] is not None
            and seg.start[2] == seg.end[2])


def _circle_from_3(p1, p2, p3):
    'Centre (cx, cy) and radius of the circle through three XY points, or None if collinear.'
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), hypot(ax - ux, ay - uy)


def _points_of(run):
    'The ordered XY vertices of a run of contiguous segments (start of first, then each end).'
    pts = [(run[0].start[0], run[0].start[1])]
    for s in run:
        pts.append((s.end[0], s.end[1]))
    return pts


def _fits_circle(pts, centre, radius, tol):
    'True when every vertex lies within tol of the circle.'
    cx, cy = centre
    return all(abs(hypot(x - cx, y - cy) - radius) <= tol for x, y in pts)


def _orientation(pts, centre):
    'True for clockwise (G2) sweep, by the sign of the total signed angle progression.'
    cx, cy = centre
    total = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        a0 = atan2(y0 - cy, x0 - cx)
        a1 = atan2(y1 - cy, x1 - cx)
        d = a1 - a0
        while d > tau / 2:
            d -= tau
        while d < -tau / 2:
            d += tau
        total += d
    return total < 0  # negative total angle -> clockwise


def _arc_length(pts, centre, radius, clockwise):
    'True swept arc length over the run (sum of per-vertex sweeps, robust to >180deg arcs).'
    cx, cy = centre
    swept = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        a0 = atan2(y0 - cy, x0 - cx)
        a1 = atan2(y1 - cy, x1 - cx)
        d = (a0 - a1) % tau if clockwise else (a1 - a0) % tau
        swept += d
    return radius * swept


def _make_arc(run, centre, radius, tol):
    'Build one arc Segment from a fittable run, conserving material exactly.'
    pts = _points_of(run)
    clockwise = _orientation(pts, centre)
    length = _arc_length(pts, centre, radius, clockwise)
    first, last = run[0], run[-1]
    vol = sum(s.deposited_volume for s in run)
    fil = sum(s.filament_length for s in run)
    # tessellate for plot rendering, matching arc_points' convention (points after the start)
    cx, cy = centre
    start_angle = atan2(first.start[1] - cy, first.start[0] - cx)
    swept = length / radius if radius else 0.0
    sign = -1 if clockwise else 1
    n = max(len(run), 2)
    tess = []
    for i in range(1, n + 1):
        if i == n:
            tess.append((last.end[0], last.end[1], last.end[2]))
        else:
            ang = start_angle + sign * swept * (i / n)
            tess.append((cx + radius * cos(ang), cy + radius * sin(ang), first.start[2]))
    return Segment(first.start, last.end, False, first.speed, length, vol, fil,
                   first.source_index, kind='arc', centre=centre, clockwise=clockwise,
                   width=first.width, height=first.height, color=last.color,
                   arc_points=tuple(tess))


def _same_context(a: Segment, b: Segment) -> bool:
    'Two fittable segments share the print context that an arc move must keep constant.'
    return (a.speed == b.speed and a.width == b.width and a.height == b.height
            and a.start[2] == b.start[2])


def _flush(run, tol, out):
    '''Try to collapse a maximal fittable run into arcs; append the result(s) to out.

    Greedily grows the largest leading sub-run that fits a single circle (>= _MIN_SEGMENTS,
    radius >= _MIN_RADIUS, chord >= _MIN_CHORD); otherwise emits the leading segment as-is and
    retries on the remainder.'''
    i = 0
    while i < len(run):
        best = None  # (end_index_exclusive, centre, radius)
        j = i + _MIN_SEGMENTS
        while j <= len(run):
            window = run[i:j]
            pts = _points_of(window)
            circ = _circle_from_3(pts[0], pts[len(pts) // 2], pts[-1])
            if circ is None:
                break
            centre, radius = circ
            if radius < _MIN_RADIUS or not _fits_circle(pts, centre, radius, tol):
                break
            chord = sum(s.length for s in window)
            if chord >= _MIN_CHORD:
                best = (j, centre, radius)
            j += 1
        if best is not None:
            end, centre, radius = best
            out.append(_make_arc(run[i:end], centre, radius, tol))
            i = end
        else:
            out.append(run[i])
            i += 1


def arc_fit(toolpath: Toolpath, tolerance: float = 0.05) -> Toolpath:
    '''Merge runs of >=3 consecutive extruding line moves that fit a common circle within
    ``tolerance`` (mm) into single G2/G3 arc Segments; material is conserved exactly. Tight
    (radius < 0.5 mm) or short (chord < 1 mm) curves are left as lines.'''
    out = []
    run = []
    for ev in toolpath.events:
        if _is_fittable(ev) and (not run or _same_context(run[-1], ev)) and (not run or run[-1].end == ev.start):
            run.append(ev)
        else:
            if run:
                _flush(run, tolerance, out)
                run = []
            if _is_fittable(ev):
                run.append(ev)
            else:
                out.append(ev)
    if run:
        _flush(run, tolerance, out)
    return Toolpath(out)


register_pass('arc_fit', arc_fit)
