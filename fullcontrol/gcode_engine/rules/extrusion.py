"""Extrusion-related verification rules: volumetric flow ceiling and over-extrusion."""
from fullcontrol.gcode_engine.verification import Issue
from fullcontrol.gcode_engine.rules._helpers import segments, extruding


def flow_rate_ceiling(toolpath, params, ctx):
    '''Flag extruding moves whose volumetric flow rate exceeds `max_flow_mm3s` (default 15 mm^3/s
    for a 0.4 mm nozzle). Flow = deposited_volume / (length / speed * 60). One warning per offending
    move, with line + segment_index; suggests slowing the move / raising the temperature.'''
    max_flow = ctx.get('max_flow_mm3s', 15.0)
    issues = []
    peak = 0.0
    peak_loc = None
    n = 0
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg) or not seg.speed or seg.speed <= 0:
            continue
        if not seg.deposited_volume or seg.deposited_volume <= 0:
            continue
        time_s = seg.length / seg.speed * 60.0
        if time_s <= 0:
            continue
        flow = seg.deposited_volume / time_s
        if flow > max_flow:
            n += 1
            if flow > peak:
                peak, peak_loc = flow, (seg_idx, line)
    if n:
        seg_idx, line = peak_loc
        issues.append(Issue('warning', 'flow_rate_ceiling',
                            f'{n} extruding move(s) exceed the {max_flow:g} mm^3/s flow ceiling '
                            f'(peak {peak:.1f} mm^3/s) - risk of under-extrusion; slow the move '
                            f'or raise the hotend temperature',
                            line=line, segment_index=seg_idx,
                            suggested_fix='adaptive_speed (lower feedrate) or higher nozzle temp'))
    return issues


def over_extrusion(toolpath, params, ctx):
    '''When width/height are known (from slicer ;WIDTH:/;HEIGHT: comments), flag moves whose
    deposited cross-section (deposited_volume / length) sits outside [0.5, 1.5] x (width x height).
    Skips moves with unknown width/height (the parser cannot recover them from E alone), so on bare
    external g-code this degrades to a no-op rather than a false positive.'''
    issues = []
    n_over = n_under = 0
    worst = None
    for seg_idx, line, seg in segments(toolpath):
        if not extruding(seg):
            continue
        if seg.width is None or seg.height is None or seg.width <= 0 or seg.height <= 0:
            continue  # cannot judge without geometry
        nominal = seg.width * seg.height
        actual = seg.deposited_volume / seg.length if seg.length else 0.0
        if nominal <= 0:
            continue
        ratio = actual / nominal
        if ratio > 1.5:
            n_over += 1
            if worst is None or ratio > worst[0]:
                worst = (ratio, seg_idx, line)
        elif ratio < 0.5:
            n_under += 1
    if n_over:
        _, seg_idx, line = worst
        issues.append(Issue('warning', 'over_extrusion',
                            f'{n_over} move(s) deposit > 1.5x the nominal width x height cross-section '
                            f'(worst {worst[0]:.2f}x) - over-extrusion',
                            line=line, segment_index=seg_idx,
                            suggested_fix='reduce flow / extrusion multiplier'))
    if n_under:
        issues.append(Issue('info', 'over_extrusion',
                            f'{n_under} move(s) deposit < 0.5x the nominal cross-section - '
                            'possible under-extrusion'))
    return issues
