"""Pre-flight validation of a design (run via transform(steps, 'validate', controls)).

A fast, best-effort safety pass over the resolved gcode step list: out-of-bounds points,
sub-zero Z, and likely cold extrusion. It reuses the gcode State so it sees the real
coordinates (including the printer's start/end procedures and primer).
"""
from fullcontrol.core.point import Point
from fullcontrol.core.extrusion_classes import Extruder
from fullcontrol.core.auxilliary_components import Hotend, Buildplate
from fullcontrol.core.printer import Printer
from fullcontrol.gcode.extrusion_classes import Retraction, Unretraction
from fullcontrol.validate.result import ValidationResult

# sanity thresholds for FDM (best-effort warnings, not hard limits)
MIN_FDM_NOZZLE_TEMP_C = 150   # most thermoplastics will not extrude below this
MAX_NOZZLE_TEMP_C = 350       # beyond a typical hotend's safe range
MAX_BED_TEMP_C = 150          # beyond a typical heated bed's range
MAX_FEEDRATE_MM_MIN = 60000   # 1000 mm/s - implausibly fast for FDM
RETRACTION_BALANCE_TOL_MM = 1e-6


def validate(steps, controls, show_tips=True) -> ValidationResult:
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.import_printer import resolve_initialization_data
    controls.initialize()
    init = resolve_initialization_data(controls.printer_name, controls.initialization_data)
    state = State(steps, controls)
    result = ValidationResult()
    _check_bounds(state.steps, init, result)
    _check_cold_extrusion(state.steps, init, result)
    _check_temperatures(state.steps, result)
    _check_speeds(state.steps, init, result)
    _check_first_layer(state.steps, result)
    _check_retraction_balance(state.steps, init, result)
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


def _check_temperatures(steps, result):
    'Flag commanded hotend/bed temperatures outside a sane FDM range.'
    for step in steps:
        if isinstance(step, Hotend) and step.temp is not None:
            if step.temp > MAX_NOZZLE_TEMP_C:
                result.add('warning', f'nozzle temperature {step.temp}C is very high (> {MAX_NOZZLE_TEMP_C}C)')
            elif step.temp < MIN_FDM_NOZZLE_TEMP_C:
                result.add('warning', f'nozzle temperature {step.temp}C is low for FDM (< {MIN_FDM_NOZZLE_TEMP_C}C) - may not extrude')
        elif isinstance(step, Buildplate) and step.temp is not None:
            if step.temp > MAX_BED_TEMP_C:
                result.add('warning', f'bed temperature {step.temp}C is very high (> {MAX_BED_TEMP_C}C)')


def _check_speeds(steps, init, result):
    'Flag non-positive feedrates (would emit F0) and implausibly fast ones.'
    speeds = [init.get('print_speed'), init.get('travel_speed')]
    for step in steps:
        if isinstance(step, Printer):
            speeds += [step.print_speed, step.travel_speed]
    for speed in speeds:
        if speed is None:
            continue
        if speed <= 0:
            result.add('error', f'print/travel speed {speed} is not positive (would emit an F0 move)')
        elif speed > MAX_FEEDRATE_MM_MIN:
            result.add('warning', f'speed {speed} mm/min is implausibly fast (> {MAX_FEEDRATE_MM_MIN} mm/min)')


def _check_first_layer(steps, result):
    'Warn if the first extruding move happens at or below z=0 (nozzle on/under the bed).'
    extruder_on = False
    tracked = Point()
    for step in steps:
        if isinstance(step, Extruder) and step.on is not None:
            extruder_on = step.on
        elif isinstance(step, Point):
            tracked.update_from(step)
            if extruder_on:
                if tracked.z is not None and tracked.z <= 0:
                    result.add('warning', f'first extrusion move is at z={tracked.z} (<= 0) - nozzle may be at or below the bed')
                return  # only the first extruding move matters


def _check_retraction_balance(steps, init, result):
    'Track retraction vs priming; warn if filament is left retracted at the end of the print.'
    default = init.get('retraction_distance') or 0
    retracted = 0.0
    for step in steps:
        if isinstance(step, Retraction):
            retracted += step.distance if step.distance is not None else default
        elif isinstance(step, Unretraction):
            primed = step.distance if step.distance is not None else retracted
            retracted = max(0.0, retracted - primed)
    if retracted > RETRACTION_BALANCE_TOL_MM:
        result.add('warning', f'{retracted:g} mm of filament is left retracted at the end of the print '
                              '(more Retraction than Unretraction) - may ooze or under-extrude on the next print')


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
