"""Thermal verification rules: cooling sanity and cold-extrusion (external-g-code aware)."""
from fullcontrol.gcode_engine.verification import Issue
from fullcontrol.gcode_engine.rules._helpers import extruding, is_planar, layer_of
from fullcontrol.ir import Segment
from fullcontrol.core.auxilliary_components import Hotend, Fan
from fullcontrol.gcode.commands import ManualGcode


def _manual_text(ev):
    'The raw text of a ManualGcode pass-through event (else "").'
    return getattr(ev, 'text', '') or '' if isinstance(ev, ManualGcode) else ''


def cooling_sanity(toolpath, params, ctx):
    '''Warn if the part-cooling fan is still off after the first layer. Fan commands arrive either
    as `Fan` events (our design IR) or as `M106`/`M107` in pass-through `ManualGcode` (parsed
    external g-code). We track the first event index at which the fan turns on and compare it to the
    index at which the second layer's first extruding move occurs. Disabled on non-planar g-code.'''
    if not is_planar(toolpath):
        return []
    layer_h = ctx.get('layer_height') or _guess_layer_height(toolpath)
    if not layer_h:
        return []
    base_z = ctx.get('base_z', 0.0)
    fan_on_at = None       # event index where fan first turned on
    second_layer_at = None  # event index where layer >= 1 extrusion starts
    second_layer_line = None
    for ev_i, ev in enumerate(toolpath.events):
        if fan_on_at is None and _fan_turns_on(ev):
            fan_on_at = ev_i
        if isinstance(ev, Segment) and extruding(ev):
            z = ev.end[2] if ev.end[2] is not None else ev.start[2]
            lyr = layer_of(z, layer_h, base_z)
            if lyr is not None and lyr >= 1 and second_layer_at is None:
                second_layer_at = ev_i
                second_layer_line = ev.source_index
    if second_layer_at is None:
        return []  # single-layer print - nothing to cool
    if fan_on_at is None or fan_on_at > second_layer_at:
        return [Issue('warning', 'cooling_sanity',
                      'part-cooling fan is still off after the first layer (no M106 / Fan before '
                      'the second layer) - overhangs and bridges may cool poorly',
                      line=second_layer_line,
                      suggested_fix='turn the fan on after the first layer (fc.Fan / M106)')]
    return []


def cold_extrusion(toolpath, params, ctx):
    '''Detect extrusion before any heating command. Heating evidence: a `Hotend` event with a temp,
    or `M104`/`M109` in pass-through `ManualGcode` (parsed external g-code) or in the printer's
    start_gcode. Reports the first extruding move that occurs with no prior heating. Emitted as an
    `error` (it is a hard print failure, not a stylistic warning).'''
    start_gcode = (ctx.get('init', {}) or {}).get('start_gcode', '') or ''
    heated = ('M104' in start_gcode) or ('M109' in start_gcode)
    for ev in toolpath.events:
        if isinstance(ev, Hotend) and getattr(ev, 'temp', None):
            heated = True
        text = _manual_text(ev)
        if 'M104' in text or 'M109' in text:
            heated = True
        if isinstance(ev, Segment) and extruding(ev) and not heated:
            return [Issue('error', 'cold_extrusion',
                          'extrusion starts before the hotend is heated (no Hotend temp or '
                          'M104/M109 seen first) - cold extrusion will jam or skip',
                          line=ev.source_index, segment_index=None,
                          suggested_fix='heat the hotend (M109 / fc.Hotend) before extruding')]
    return []


def _fan_turns_on(ev):
    if isinstance(ev, Fan) and getattr(ev, 'speed_percent', None):
        return ev.speed_percent > 0
    text = ''
    if isinstance(ev, ManualGcode):
        text = (getattr(ev, 'text', '') or '').upper()
    if 'M106' in text:
        # M106 with no S, or S>0, turns the fan on; M106 S0 is off
        import re
        m = re.search(r'\bS(\d+(?:\.\d+)?)', text)
        return (m is None) or (float(m.group(1)) > 0)
    return False


def _guess_layer_height(toolpath):
    zs = []
    for ev in toolpath.events:
        if isinstance(ev, Segment) and extruding(ev) and ev.end[2] is not None:
            zs.append(ev.end[2])
    if len(zs) < 2:
        return None
    diffs = sorted({round(b - a, 4) for a, b in zip(zs, zs[1:]) if b - a > 1e-4})
    return diffs[0] if diffs else None
