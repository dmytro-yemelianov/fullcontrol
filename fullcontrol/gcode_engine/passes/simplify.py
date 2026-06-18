"""``simplify`` - Ramer-Douglas-Peucker on straight runs of extruding line moves.

A run of consecutive extruding line segments that share print context (speed/width/height/Z) is a
polyline. RDP drops intermediate vertices whose perpendicular deviation from the simplified chord
is below ``tolerance`` (mm), collapsing the moves between two kept vertices into one segment whose
``deposited_volume``/``filament_length``/``length`` are the *sums* of the moves it replaces - so
material is conserved exactly and the path never deviates from the original by more than
``tolerance``.
"""
from math import hypot

from fullcontrol.ir.passes import register_pass
from fullcontrol.ir.toolpath import Segment, Toolpath


def _splittable(seg: Segment) -> bool:
    'A planar extruding straight move with fully-defined XY endpoints.'
    return (isinstance(seg, Segment) and seg.kind == 'line' and not seg.travel
            and seg.start[0] is not None and seg.start[1] is not None
            and seg.end[0] is not None and seg.end[1] is not None
            and seg.start[2] == seg.end[2])


def _same_context(a: Segment, b: Segment) -> bool:
    return (a.speed == b.speed and a.width == b.width and a.height == b.height
            and a.start[2] == b.start[2] and a.end == b.start)


def _perp_dist(p, a, b):
    'Perpendicular distance of XY point p from the segment a->b.'
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    den = hypot(dx, dy)
    if den < 1e-12:
        return hypot(px - ax, py - ay)
    return abs(dy * px - dx * py + bx * ay - by * ax) / den


def _rdp_keep(pts, tol):
    'Indices of the vertices RDP keeps for a polyline of XY points (endpoints always kept).'
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        dmax, idx = 0.0, -1
        for i in range(lo + 1, hi):
            d = _perp_dist(pts[i], pts[lo], pts[hi])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol and idx != -1:
            keep[idx] = True
            stack.append((lo, idx))
            stack.append((idx, hi))
    return keep


def _merge(run, lo, hi):
    'Merge run[lo:hi+1] (segment indices) into one Segment, summing material and length.'
    first, last = run[lo], run[hi]
    length = sum(s.length for s in run[lo:hi + 1])
    vol = sum(s.deposited_volume for s in run[lo:hi + 1])
    fil = sum(s.filament_length for s in run[lo:hi + 1])
    return Segment(first.start, last.end, False, first.speed, length, vol, fil,
                   first.source_index, kind='line', width=first.width,
                   height=first.height, color=last.color)


def _simplify_run(run, tol, out):
    'RDP-simplify one contiguous run of splittable segments into out.'
    if len(run) < 2:
        out.extend(run)
        return
    pts = [(run[0].start[0], run[0].start[1])]
    for s in run:
        pts.append((s.end[0], s.end[1]))
    keep = _rdp_keep(pts, tol)
    kept_vertices = [i for i, k in enumerate(keep) if k]  # vertex indices into pts
    # segment i spans vertices i..i+1; merge between consecutive kept vertices
    for a, b in zip(kept_vertices, kept_vertices[1:]):
        out.append(_merge(run, a, b - 1))


def simplify(toolpath: Toolpath, tolerance: float = 0.01) -> Toolpath:
    '''Ramer-Douglas-Peucker simplification of straight runs of extruding line moves: drop
    intermediate points whose deviation is below ``tolerance`` (mm), merging the spanned moves
    into one (material conserved, geometric deviation <= tolerance).'''
    out = []
    run = []
    for ev in toolpath.events:
        if _splittable(ev) and (not run or _same_context(run[-1], ev)):
            run.append(ev)
        else:
            if run:
                _simplify_run(run, tolerance, out)
                run = []
            if _splittable(ev):
                run.append(ev)
            else:
                out.append(ev)
    if run:
        _simplify_run(run, tolerance, out)
    return Toolpath(out)


register_pass('simplify', simplify)
