"""gcode emission as a renderer (functools.singledispatch) rather than a .gcode()
method on every step class.

The driver dispatches each step through render_gcode(step, state). A step with no
gcode representation (e.g. a plot-only annotation) falls through to the default
handler and emits nothing. This keeps the step classes as data and centralises the
gcode backend here, so the same classes can be rendered by other backends too.
"""
from functools import singledispatch

from fullcontrol.common import Printer as CommonPrinter
from fullcontrol.gcode.point import Point
from fullcontrol.gcode.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion
from fullcontrol.gcode.auxilliary_components import Fan, Hotend, Buildplate, MAX_FAN_PWM, PERCENT
from fullcontrol.gcode.commands import PrinterCommand, ManualGcode
from fullcontrol.gcode.annotations import GcodeComment
from fullcontrol.gcode.number_format import fmt


@singledispatch
def render_gcode(step, state):
    'default: a step with no gcode representation emits nothing'
    return None


@render_gcode.register
def _(step: Point, state):
    XYZ_str = step.XYZ_gcode(state.point)
    if XYZ_str is not None:  # only write a line of gcode if movement occurs
        G_str = 'G1 ' if state.extruder.on or state.extruder.travel_format == "G1_E0" else 'G0 '
        F_str = state.printer.f_gcode(state)
        E_str = state.extruder.e_gcode(step, state)
        gcode_str = f'{G_str}{F_str}{XYZ_str}{E_str}'
        state.printer.speed_changed = False
        state.point.update_from(step)
        return gcode_str.strip()  # strip the final space


@render_gcode.register
def _(step: CommonPrinter, state):  # covers the gcode Printer and the multiaxis MultiaxisPrinter
    state.printer.update_from(step)
    if step.print_speed is not None or step.travel_speed is not None:
        state.printer.speed_changed = True
    if step.new_command is not None:
        state.printer.command_list = {**(state.printer.command_list or {}), **step.new_command}


@render_gcode.register
def _(step: Extruder, state):
    state.extruder.update_from(step)
    if step.on is not None:  # printing/moving strategy may have changed
        state.printer.speed_changed = True
    if step.units is not None or step.dia_feed is not None:
        state.extruder.update_e_ratio()
    if step.relative_gcode is not None:
        state.extruder.total_volume_ref = state.extruder.total_volume
        return "M83 ; relative extrusion" if state.extruder.relative_gcode is True \
            else "M82 ; absolute extrusion\nG92 E0 ; reset extrusion position to zero"


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
def _(step: Fan, state):
    if step.speed_percent is not None:
        return f'M106 S{int(step.speed_percent * MAX_FAN_PWM / PERCENT)} ; set fan speed'


@render_gcode.register
def _(step: Hotend, state):
    if step.temp is None:
        return None  # no temperature to set
    if step.tool is None:
        return f'M104 S{step.temp} ; set hotend temp and continue' if step.wait is False \
            else f'M109 S{step.temp} ; set hotend temp and wait'
    return f'M104 S{step.temp} T{step.tool} ; set hotend temp for tool {step.tool} and continue' if step.wait is False \
        else f'M109 S{step.temp} T{step.tool} ; set hotend temp for tool {step.tool} and wait'


@render_gcode.register
def _(step: Buildplate, state):
    if step.temp is None:
        return None  # no temperature to set
    return f'M140 S{step.temp} ; set bed temp and continue' if step.wait is False \
        else f'M190 S{step.temp} ; set bed temp and wait'


@render_gcode.register
def _(step: PrinterCommand, state):
    # only valid after a Printer with a command_list has updated state.printer
    return state.printer.command_list[step.id]


@render_gcode.register
def _(step: ManualGcode, state):
    if step.text is not None:
        return step.text


@render_gcode.register
def _(step: GcodeComment, state):
    if step.end_of_previous_line_text is not None and state.gcode:
        state.gcode[-1] += ' ; ' + step.end_of_previous_line_text
    if step.text is not None:
        return '; ' + step.text
