"""First-layer adhesion verification rule."""
from fullcontrol.gcode_engine.verification import Issue
from fullcontrol.gcode_engine.rules._helpers import segments, extruding, is_planar, layer_of


def first_layer_adhesion(toolpath, params, ctx):
    '''Two adhesion heuristics over the first extruding layer:

    * first-layer print speed should be slower (<= ~80% of the median later-layer speed). Printing
      the first layer as fast as the rest hurts bed adhesion.
    * the first layer's z should be near one layer height (not far above the bed).

    Disabled on non-planar g-code. Each emitted as a `warning` (speed) / `info` (z).'''
    if not is_planar(toolpath):
        return []
    layer_h = ctx.get('layer_height') or _guess_layer_height(toolpath)
    if not layer_h:
        return []
    base_z = ctx.get('base_z', 0.0)
    first_speeds = []
    later_speeds = []
    first_line = None
    first_seg = None
    first_z = None
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg) or not seg.speed or seg.speed <= 0:
            continue
        z = seg.end[2] if seg.end[2] is not None else seg.start[2]
        lyr = layer_of(z, layer_h, base_z)
        if lyr is None:
            continue
        if lyr <= 0:
            first_speeds.append(seg.speed)
            if first_line is None:
                first_line, first_seg, first_z = line, seg_idx, z
        else:
            later_speeds.append(seg.speed)
    issues = []
    if first_speeds and later_speeds:
        f = _median(first_speeds)
        l = _median(later_speeds)
        if l > 0 and f > 0.8 * l:
            issues.append(Issue('warning', 'first_layer_adhesion',
                                f'first-layer speed ({f:.0f} mm/min) is not slowed relative to later '
                                f'layers ({l:.0f} mm/min) - slower first-layer speed improves bed '
                                f'adhesion',
                                line=first_line, segment_index=first_seg,
                                suggested_fix='reduce first-layer print speed (<= 50-80% of later layers)'))
    if first_z is not None and first_z > 1.5 * layer_h:
        issues.append(Issue('info', 'first_layer_adhesion',
                            f'first extruding layer is at z={first_z:.2f} mm, well above one layer '
                            f'height ({layer_h:.2f} mm) - may not adhere to the bed',
                            line=first_line, segment_index=first_seg))
    return issues


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _guess_layer_height(toolpath):
    zs = []
    for _, _, seg in segments(toolpath):
        if extruding(seg) and seg.end[2] is not None:
            zs.append(seg.end[2])
    if len(zs) < 2:
        return None
    diffs = sorted({round(b - a, 4) for a, b in zip(zs, zs[1:]) if b - a > 1e-4})
    return diffs[0] if diffs else None
