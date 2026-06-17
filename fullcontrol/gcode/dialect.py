"""The gcode backend as a dialect over the Toolpath IR.

Motion (G0/G1/G2/G3) is emitted from the resolved `Segment`s; the gcode-specific emission
state that cannot live in the shared IR - the E accumulator, retraction running state, the
feedrate-change suppression, the command list and comment-append - is held by the running
gcode `State` (`dstate`), reused for the non-motion events via the existing render_gcode
handlers. So motion's position/geometry/speed come from the one shared `resolve()` pass, while
the firmware vocabulary comes from the flavor and the E/command state from `dstate`.
"""
from fullcontrol.gcode.number_format import fmt
from fullcontrol.gcode.renderers import render_gcode
from fullcontrol.ir import Segment, MaterialEvent


def _axes(start, end) -> str:
    'X/Y/Z words for the axes that are defined and changed (matches the old _xyz_gcode).'
    s = ''
    for label, a, b in (('X', start[0], end[0]), ('Y', start[1], end[1]), ('Z', start[2], end[2])):
        if b is not None and b != a:
            s += f'{label}{fmt(b)} '
    return s


def _e_word(dstate, deposited_volume, travel) -> str:
    'E word for a move (mirrors Extruder.e_gcode): cumulative via the shared E accumulator.'
    e = dstate.extruder
    if not travel:
        return f'E{fmt(e.get_and_update_volume(deposited_volume) * e.volume_to_e)}'
    if e.travel_format == 'G1_E0':
        return f'E{fmt(e.get_and_update_volume(0) * e.volume_to_e)}'
    return ''


def _emit_segment(seg, dstate):
    'Emit a motion line (G0/G1 line, or G2/G3 arc) from a resolved Segment.'
    f_str = f'F{fmt(seg.speed, dp=1)} ' if dstate.printer.speed_changed else ''
    e_str = _e_word(dstate, seg.deposited_volume, seg.travel)
    if seg.kind == 'arc':
        coords = f'X{fmt(seg.end[0])} Y{fmt(seg.end[1])} '
        if seg.end[2] is not None and seg.end[2] != seg.start[2]:
            coords += f'Z{fmt(seg.end[2])} '
        ij = f'I{fmt(seg.centre[0] - seg.start[0])} J{fmt(seg.centre[1] - seg.start[1])} '
        line = dstate.flavor.arc_move(seg.clockwise, f_str, coords, ij, e_str)
    else:
        line = dstate.flavor.linear_move(not seg.travel, f_str, _axes(seg.start, seg.end), e_str)
    dstate.printer.speed_changed = False
    return line


def _emit_material(mev, dstate):
    'Emit a stationary-extrusion line (mirrors the StationaryExtrusion renderer).'
    dstate.printer.speed_changed = True
    return f'G1 F{mev.speed} E{fmt(dstate.extruder.get_and_update_volume(mev.deposited_volume) * dstate.extruder.volume_to_e)}'


def gcode_from_ir(toolpath, dstate) -> list:
    'Fold the Toolpath into gcode lines (appended to dstate.gcode for comment-append support).'
    for ev in toolpath.events:
        try:
            if isinstance(ev, Segment):
                line = _emit_segment(ev, dstate)
            elif isinstance(ev, MaterialEvent):
                line = _emit_material(ev, dstate)
            else:  # a pass-through non-motion step - reuse its existing render_gcode handler
                line = render_gcode(ev, dstate)
        except Exception as e:
            raise type(e)(f'error generating gcode for {type(ev).__name__}: {e}') from e
        if line is not None:
            dstate.gcode.append(line)
    return dstate.gcode
