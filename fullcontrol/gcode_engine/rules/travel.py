"""Travel-related verification rules: travel density, seam clustering, retraction balance."""
from fullcontrol.gcode_engine.verification import Issue
from fullcontrol.gcode_engine.rules._helpers import segments, extruding, is_planar, layer_of
from fullcontrol.gcode.extrusion_classes import Retraction, Unretraction


def travel_density(toolpath, params, ctx):
    '''Flag a high ratio of travel distance to extruding distance (> 0.3). A lot of travel relative
    to printing usually means the path ordering is inefficient - suggests `travel_reorder`.'''
    travel_dist = 0.0
    extrude_dist = 0.0
    for _, _, seg in segments(toolpath):
        if seg.length is None or seg.length <= 0:
            continue
        if seg.travel:
            travel_dist += seg.length
        elif extruding(seg):
            extrude_dist += seg.length
    if extrude_dist <= 0:
        return []
    ratio = travel_dist / extrude_dist
    if ratio > 0.3:
        return [Issue('info', 'travel_density',
                      f'travel/extrude distance ratio is {ratio:.2f} (> 0.30) - path ordering may '
                      f'be inefficient',
                      suggested_fix='travel_reorder')]
    return []


def seam_clustering(toolpath, params, ctx):
    '''Detect scattered layer-change positions: if the XY point where each layer starts varies by
    more than 5 mm, the seam is not aligned and leaves a visible scar. Disabled on non-planar
    g-code (no discrete layers). Emitted as `info`.'''
    if not is_planar(toolpath):
        return []
    layer_h = ctx.get('layer_height') or _guess_layer_height(toolpath)
    if not layer_h:
        return []
    base_z = ctx.get('base_z', 0.0)
    # the first extruding XY of each layer is its seam
    seam = {}  # layer -> (x, y, line, seg_idx)
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg) or None in seg.start[:2]:
            continue
        lyr = layer_of(seg.end[2] if seg.end[2] is not None else seg.start[2], layer_h, base_z)
        if lyr is None or lyr in seam:
            continue
        seam[lyr] = (seg.start[0], seg.start[1], line, seg_idx)
    if len(seam) < 3:
        return []
    xs = [v[0] for v in seam.values()]
    ys = [v[1] for v in seam.values()]
    scatter = max(((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5, 0.0)
    if scatter > 5.0:
        # report at the first layer's seam
        first = seam[min(seam)]
        return [Issue('info', 'seam_clustering',
                      f'layer-start (seam) positions scatter by {scatter:.1f} mm (> 5 mm) - the '
                      f'seam is not aligned and may leave a visible scar',
                      line=first[2], segment_index=first[3])]
    return []


def retraction_balance(toolpath, params, ctx):
    '''Thin wrapper over the existing `validate.run._check_retraction_balance` rule: track retract
    vs prime over the toolpath's events and warn if filament is left retracted at the end. On a
    parsed external g-code these come through as pass-through `Retraction`/`Unretraction` events
    only when the g-code used the dialect's retract/unretract step shapes; otherwise this no-ops.'''
    from fullcontrol.validate.result import ValidationResult
    from fullcontrol.validate.run import _check_retraction_balance
    has_retraction = any(isinstance(e, (Retraction, Unretraction)) for e in toolpath.events)
    if not has_retraction:
        return []
    vr = ValidationResult()
    _check_retraction_balance(toolpath.events, ctx.get('init', {}) or {}, vr)
    return [Issue(i['severity'], 'retraction_balance', i['message']) for i in vr.issues]


def _guess_layer_height(toolpath):
    zs = []
    for _, _, seg in segments(toolpath):
        if extruding(seg) and seg.end[2] is not None:
            zs.append(seg.end[2])
    if len(zs) < 2:
        return None
    diffs = sorted({round(b - a, 4) for a, b in zip(zs, zs[1:]) if b - a > 1e-4})
    return diffs[0] if diffs else None
