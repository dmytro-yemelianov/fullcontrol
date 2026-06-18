"""Geometric verification rules: overhang detection and arc-fit opportunities."""
from fullcontrol.gcode_engine.verification import Issue
from fullcontrol.gcode_engine.rules._helpers import segments, extruding, is_planar, layer_of


def overhang_angle(toolpath, params, ctx):
    '''Approximate overhang check: extruding XY that lands beyond the previous layer's footprint by
    more than half a line width is likely an unsupported overhang. This is a coarse hull-extent
    comparison (per-axis bounding box), not a true geometric overhang - precise analysis needs the
    source mesh. Disabled on non-planar g-code (it has no discrete layers). Emitted as `info`.'''
    if not is_planar(toolpath):
        return [Issue('info', 'overhang_angle',
                      'non-planar g-code (>50% of moves change z) - overhang check disabled')]
    layer_h = ctx.get('layer_height') or _guess_layer_height(toolpath)
    if not layer_h:
        return []
    base_z = ctx.get('base_z', 0.0)
    half_width = (ctx.get('default_width') or 0.4) / 2.0
    # accumulate the XY bounding box of extruded material per layer
    extents = {}  # layer -> [minx, miny, maxx, maxy]
    order = []
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg) or None in seg.end[:2]:
            continue
        z = seg.end[2]
        lyr = layer_of(z, layer_h, base_z)
        if lyr is None:
            continue
        x, y = seg.end[0], seg.end[1]
        if lyr not in extents:
            extents[lyr] = [x, y, x, y]
            order.append(lyr)
        else:
            e = extents[lyr]
            e[0], e[1] = min(e[0], x), min(e[1], y)
            e[2], e[3] = max(e[2], x), max(e[3], y)
    issues = []
    n = 0
    first_loc = None
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg) or None in seg.end[:2]:
            continue
        lyr = layer_of(seg.end[2], layer_h, base_z)
        if lyr is None or (lyr - 1) not in extents:
            continue
        px0, py0, px1, py1 = extents[lyr - 1]
        x, y = seg.end[0], seg.end[1]
        if (x < px0 - half_width or x > px1 + half_width
                or y < py0 - half_width or y > py1 + half_width):
            n += 1
            if first_loc is None:
                first_loc = (seg_idx, line)
    if n:
        seg_idx, line = first_loc
        issues.append(Issue('info', 'overhang_angle',
                            f'{n} extruding move(s) extend beyond the previous layer footprint by '
                            f'> half a line width - possible unsupported overhang (approx; provide '
                            f'the source mesh for precise analysis)',
                            line=line, segment_index=seg_idx))
    return issues


def arc_opportunity(toolpath, params, ctx):
    '''Flag runs of > 4 consecutive straight extruding segments that fit a common circle within
    0.05 mm - candidates for arc fitting (G2/G3), which shrinks the g-code and smooths motion.
    Emitted as `info`, suggesting the `arc_fit` optimisation pass.'''
    tol = ctx.get('arc_tol', 0.05)
    min_run = 5
    issues = []
    run = []  # list of (seg_idx, line, (x,y)) for consecutive straight extruding segs
    best = None  # (run_length, seg_idx, line)
    total_arcs = 0

    def flush(run):
        nonlocal best, total_arcs
        if len(run) >= min_run:
            pts = [r[2] for r in run]
            if _fits_circle(pts, tol):
                total_arcs += 1
                if best is None or len(run) > best[0]:
                    best = (len(run), run[0][0], run[0][1])

    for seg_idx, line, seg in segments(toolpath):
        if seg.kind == 'line' and extruding(seg) and None not in seg.end[:2] and None not in seg.start[:2]:
            if not run:
                run.append((seg_idx, line, (seg.start[0], seg.start[1])))
            run.append((seg_idx, line, (seg.end[0], seg.end[1])))
        else:
            flush(run)
            run = []
    flush(run)

    if best:
        run_len, seg_idx, line = best
        issues.append(Issue('info', 'arc_opportunity',
                            f'{total_arcs} run(s) of consecutive straight moves fit a common circle '
                            f'within {tol} mm (longest {run_len} moves) - candidate(s) for arc '
                            f'fitting (G2/G3)',
                            line=line, segment_index=seg_idx,
                            suggested_fix='arc_fit'))
    return issues


def _guess_layer_height(toolpath):
    'Estimate a layer height from the smallest positive z-step between extruding moves.'
    zs = []
    for _, _, seg in segments(toolpath):
        if extruding(seg) and seg.end[2] is not None:
            zs.append(seg.end[2])
    if len(zs) < 2:
        return None
    diffs = sorted({round(b - a, 4) for a, b in zip(zs, zs[1:]) if b - a > 1e-4})
    return diffs[0] if diffs else None


def _fits_circle(pts, tol):
    '''True if all points lie within `tol` of a least-squares circle through them. Uses the
    algebraic (Kasa) fit; rejects near-collinear point sets (huge radius / unstable fit).'''
    if len(pts) < 3:
        return False
    import numpy as np
    p = np.asarray(pts, dtype=float)
    x, y = p[:, 0], p[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return False
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 0:
        return False
    r = r2 ** 0.5
    if r > 1e4:  # essentially a straight line - not an arc opportunity
        return False
    radii = np.hypot(x - cx, y - cy)
    return bool(np.all(np.abs(radii - r) <= tol))
