"""gcode emission as a renderer (functools.singledispatch) rather than a .gcode()
method on every step class.

The driver dispatches each step through render_gcode(step, state). A step with no
gcode representation (e.g. a plot-only annotation) falls through to the default
handler and emits nothing. This keeps the step classes as data and centralises the
gcode backend here, so the same classes can be rendered by other backends too.
"""
from functools import singledispatch

# handlers are registered on the core (backend-free) data classes so that designs built from
# core classes - e.g. by the geometry generators - render identically to ones using the
# combined backend classes (which are subclasses and resolve to the same handlers via the MRO)
from fullcontrol.common import Printer as CommonPrinter
from fullcontrol.core.arc import arc_geometry
from fullcontrol.core.point import Point
from fullcontrol.gcode.arc import Arc
from fullcontrol.core.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion
from fullcontrol.gcode.extrusion_classes import Retraction, Unretraction
from fullcontrol.core.auxilliary_components import Fan, Hotend, Buildplate
from fullcontrol.gcode.commands import PrinterCommand, ManualGcode, Acceleration, Jerk, PressureAdvance
from fullcontrol.gcode.annotations import GcodeComment
from fullcontrol.gcode.number_format import fmt


@singledispatch
def render_gcode(step, state):
    'default: a step with no gcode representation emits nothing'
    return None


def _xyz_gcode(step, prev) -> str:
    'XYZ words to move from prev to step (only axes that are defined and changed); None if no move.'
    s = ''
    if step.x is not None and step.x != prev.x:
        s += f'X{fmt(step.x)} '
    if step.y is not None and step.y != prev.y:
        s += f'Y{fmt(step.y)} '
    if step.z is not None and step.z != prev.z:
        s += f'Z{fmt(step.z)} '
    return s if s != '' else None


@render_gcode.register
def _(step: Point, state):
    XYZ_str = _xyz_gcode(step, state.point)
    if XYZ_str is not None:  # only write a line of gcode if movement occurs
        G_str = 'G1 ' if state.extruder.on or state.extruder.travel_format == "G1_E0" else 'G0 '
        F_str = state.printer.f_gcode(state)
        E_str = state.extruder.e_gcode(step, state)
        gcode_str = f'{G_str}{F_str}{XYZ_str}{E_str}'
        state.printer.speed_changed = False
        state.point.update_from(step)
        return gcode_str.strip()  # strip the final space


@render_gcode.register
def _(step: Arc, state):
    start = state.point
    geom = arc_geometry(step, start.x, start.y, start.z)
    coords = f'X{fmt(step.end.x)} Y{fmt(step.end.y)} '
    if step.end.z is not None and step.end.z != start.z:
        coords += f'Z{fmt(step.end.z)} '
    G_str = 'G2 ' if geom.clockwise else 'G3 '
    F_str = state.printer.f_gcode(state)
    IJ_str = f'I{fmt(geom.cx - start.x)} J{fmt(geom.cy - start.y)} '
    E_str = _arc_e_gcode(state, geom.arc_length)
    state.printer.speed_changed = False
    state.point.update_from(step.end)
    return f'{G_str}{F_str}{coords}{IJ_str}{E_str}'.strip()


def _arc_e_gcode(state, arc_length: float) -> str:
    'E word for an arc move of the given length, mirroring Extruder.e_gcode for straight moves'
    e = state.extruder
    if e.on:
        return f'E{fmt(e.get_and_update_volume(arc_length * state.extrusion_geometry.area) * e.volume_to_e)}'
    if e.travel_format == 'G1_E0':
        return f'E{fmt(e.get_and_update_volume(0) * e.volume_to_e)}'
    return ''


@render_gcode.register
def _(step: CommonPrinter, state):  # covers the gcode Printer and the multiaxis MultiaxisPrinter
    state.printer.update_from(step)
    if step.print_speed is not None or step.travel_speed is not None:
        state.printer.speed_changed = True
    if getattr(step, 'new_command', None) is not None:  # new_command is a gcode-Printer field
        state.printer.command_list = {**(state.printer.command_list or {}), **step.new_command}


@render_gcode.register
def _(step: Extruder, state):
    state.extruder.update_from(step)
    if step.on is not None:  # printing/moving strategy may have changed
        state.printer.speed_changed = True
    # units/dia_feed/relative_gcode are gcode-Extruder fields; a core Extruder lacks them
    if getattr(step, 'units', None) is not None or getattr(step, 'dia_feed', None) is not None:
        state.extruder.update_e_ratio()
    if getattr(step, 'relative_gcode', None) is not None:
        state.extruder.total_volume_ref = state.extruder.total_volume
        return state.flavor.extrusion_mode(state.extruder.relative_gcode)


@render_gcode.register
def _(step: ExtrusionGeometry, state):
    state.extrusion_geometry.update_from(step)
    if step.width is not None or step.height is not None or step.diameter is not None or step.area_model is not None:
        try:
            state.extrusion_geometry.update_area()
        except TypeError:
            pass  # in case not all parameters set yet (None arithmetic)


@render_gcode.register
def _(step: StationaryExtrusion, state):
    state.printer.speed_changed = True
    return f'G1 F{step.speed} E{fmt(state.extruder.get_and_update_volume(step.volume)*state.extruder.volume_to_e)}'


@render_gcode.register
def _(step: Retraction, state):
    e = state.extruder
    distance = step.distance if step.distance is not None else e.retraction_distance
    speed = step.speed if step.speed is not None else e.retraction_speed
    if not distance:  # nothing to retract -> emit no line
        return None
    # remember as the running default so a later Retraction()/Unretraction() inherits it
    e.retraction_distance, e.retraction_speed = distance, speed
    e.retracted_length += distance
    # distance is filament-length; convert to a volume so the E machinery (relative/absolute,
    # volume_to_e) emits the matching -E delta. volume * volume_to_e == -distance.
    volume = -distance / e.volume_to_e
    state.printer.speed_changed = True
    return f'G1 F{fmt(speed, dp=1)} E{fmt(e.get_and_update_volume(volume) * e.volume_to_e)} ; retract'


@render_gcode.register
def _(step: Unretraction, state):
    e = state.extruder
    distance = step.distance if step.distance is not None else e.retracted_length
    speed = step.speed if step.speed is not None else e.retraction_speed
    if not distance:  # nothing primed -> emit no line
        return None
    e.retracted_length = max(0.0, e.retracted_length - distance)
    volume = distance / e.volume_to_e
    state.printer.speed_changed = True
    return f'G1 F{fmt(speed, dp=1)} E{fmt(e.get_and_update_volume(volume) * e.volume_to_e)} ; unretract'


@render_gcode.register
def _(step: Fan, state):
    if step.speed_percent is not None:
        return state.flavor.fan(step.speed_percent)


@render_gcode.register
def _(step: Hotend, state):
    if step.temp is None:
        return None  # no temperature to set
    return state.flavor.hotend_temp(step.temp, step.wait, step.tool)


@render_gcode.register
def _(step: Buildplate, state):
    if step.temp is None:
        return None  # no temperature to set
    return state.flavor.bed_temp(step.temp, step.wait)


@render_gcode.register
def _(step: PrinterCommand, state):
    # only valid after a Printer with a command_list has updated state.printer
    return state.printer.command_list[step.id]


@render_gcode.register
def _(step: ManualGcode, state):
    if step.text is not None:
        return step.text


@render_gcode.register
def _(step: Acceleration, state):
    return state.flavor.acceleration(step.printing, step.retract, step.travel)


@render_gcode.register
def _(step: Jerk, state):
    return state.flavor.jerk(step.x, step.y, step.z, step.e)


@render_gcode.register
def _(step: PressureAdvance, state):
    return state.flavor.pressure_advance(step.value, step.tool)


@render_gcode.register
def _(step: GcodeComment, state):
    if step.end_of_previous_line_text is not None and state.gcode:
        state.gcode[-1] += ' ; ' + step.end_of_previous_line_text
    if step.text is not None:
        return '; ' + step.text
