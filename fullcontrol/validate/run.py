"""Pre-flight validation of a design (run via transform(steps, 'validate', controls)).

A fast, best-effort safety pass over the resolved gcode step list: out-of-bounds points,
sub-zero Z, and likely cold extrusion. It reuses the gcode State so it sees the real
coordinates (including the printer's start/end procedures and primer).
"""
from fullcontrol.core.point import Point
from fullcontrol.core.extrusion_classes import Extruder
from fullcontrol.core.auxilliary_components import Hotend
from fullcontrol.validate.result import ValidationResult


def validate(steps, controls, show_tips=True) -> ValidationResult:
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.import_printer import resolve_initialization_data
    controls.initialize()
    init = resolve_initialization_data(controls.printer_name, controls.initialization_data)
    state = State(steps, controls)
    result = ValidationResult()
    _check_bounds(state.steps, init, result)
    _check_cold_extrusion(state.steps, init, result)
    return result


def _check_bounds(steps, init, result):
    bx, by, bz = init.get('build_volume_x'), init.get('build_volume_y'), init.get('build_volume_z')
    if not (bx and by and bz):
        result.add('info', 'build volume not defined for this printer - out-of-bounds check skipped '
                           "(pass initialization_data={'build_volume_x':.., 'build_volume_y':.., 'build_volume_z':..})")
        return
    tracked = Point()
    n_out = n_subzero_z = 0
    first_out = None
    for step in steps:
        if isinstance(step, Point):
            tracked.update_from(step)
            x, y, z = tracked.x, tracked.y, tracked.z
            outside = ((x is not None and not (0 <= x <= bx)) or
                       (y is not None and not (0 <= y <= by)) or
                       (z is not None and not (0 <= z <= bz)))
            if outside:
                n_out += 1
                if first_out is None:
                    first_out = (x, y, z)
            if z is not None and z < 0:
                n_subzero_z += 1
    if n_out:
        result.add('error', f'{n_out} point(s) outside the build volume ({bx}x{by}x{bz}); '
                            f'first at (x={first_out[0]}, y={first_out[1]}, z={first_out[2]})')
    if n_subzero_z:
        result.add('warning', f'{n_subzero_z} point(s) have negative z (below the bed)')


def _check_cold_extrusion(steps, init, result):
    # heating evidence: a Hotend step with a temperature, or M104/M109 in the printer's start gcode template
    start_gcode = init.get('start_gcode', '') or ''
    heated = ('M104' in start_gcode) or ('M109' in start_gcode)
    extruder_on = False
    prev = Point()
    for step in steps:
        if isinstance(step, Hotend) and step.temp:
            heated = True
        elif isinstance(step, Extruder) and step.on is not None:
            extruder_on = step.on
        elif isinstance(step, Point):
            moved = any(getattr(step, ax) is not None and getattr(step, ax) != getattr(prev, ax) for ax in 'xyz')
            if extruder_on and moved and not heated:
                result.add('warning', 'extrusion appears to start before the hotend is heated '
                                      '(no Hotend temperature or M104/M109 seen) - risk of cold extrusion')
                return  # report once
            prev.update_from(step)
