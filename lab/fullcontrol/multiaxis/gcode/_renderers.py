"""Register the multiaxis Point variants with the shared gcode renderer.

Importing this module registers handlers; the shared step classes (Extruder, Fan,
Printer, ...) are already handled by fullcontrol.gcode.renderers. The Printer handler
there is registered on the common Printer base, so it also covers MultiaxisPrinter.
"""
from fullcontrol.gcode.renderers import render_gcode
from lab.fullcontrol.multiaxis.gcode.XYZB.point import Point as XYZBPoint
from lab.fullcontrol.multiaxis.gcode.XYZBC.point import Point as XYZBCPoint
from lab.fullcontrol.multiaxis.gcode.XYZC0B1.point import Point as XYZC0B1Point


def _render_multiaxis_point(step, state, axis_gcode_method):
    self_systemXYZ = step.inverse_kinematics(state)
    axis_str = getattr(step, axis_gcode_method)(self_systemXYZ, state.point_systemXYZ)
    if axis_str is not None:  # only write a line of gcode if movement occurs
        G_str = 'G1 ' if state.extruder.on else 'G0 '
        F_str = state.printer.f_gcode(state)
        E_str = state.extruder.e_gcode(step, state)
        gcode_str = f'{G_str}{F_str}{axis_str}{E_str}'
        state.printer.speed_changed = False
        state.point.update_from(step)
        state.point_systemXYZ.update_from(self_systemXYZ)
        return gcode_str.strip()


@render_gcode.register
def _(step: XYZBPoint, state):
    return _render_multiaxis_point(step, state, 'XYZB_gcode')


@render_gcode.register
def _(step: XYZBCPoint, state):
    return _render_multiaxis_point(step, state, 'XYZBC_gcode')


@render_gcode.register
def _(step: XYZC0B1Point, state):
    return _render_multiaxis_point(step, state, 'XYZBC_gcode')
