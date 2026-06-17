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
TRAVEL_STRINGING_THRESHOLD_MM = 2.0   # travels longer than this typically warrant a retraction


def _xy_distance(a: Point, b: Point) -> float:
    if None in (a.x, a.y, b.x, b.y):
        return 0.0
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def validate(steps, controls, show_tips=True) -> ValidationResult:
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.import_printer import resolve_initialization_data
    from fullcontrol.ir import resolve, Segment
    controls.initialize()
    init = resolve_initialization_data(controls.printer_name, controls.initialization_data)
    state = State(steps, controls)
    # geometric checks consume the resolved Toolpath IR (one shared resolve pass); config /
    # ordering checks still walk the resolved step list (they are about commanded values/order)
    segments = [e for e in resolve(steps, controls).events if isinstance(e, Segment)]
    result = ValidationResult()
    _check_bounds(segments, init, result)
    _check_first_layer(segments, result)
    _check_extrusion_geometry(segments, result)
    _check_cold_extrusion(state.steps, init, result)
    _check_temperatures(state.steps, result)
    _check_speeds(state.steps, init, result)
    _check_retraction_balance(state.steps, init, result)
    _check_stringing(state.steps, result)
    return result


def _check_bounds(segments, init, result):
    'Out-of-bounds and negative-z, over the resolved move endpoints.'
    bx, by, bz = init.get('build_volume_x'), init.get('build_volume_y'), init.get('build_volume_z')
    if not (bx and by and bz):
        result.add('info', 'build volume not defined for this printer - out-of-bounds check skipped '
                           "(pass initialization_data={'build_volume_x':.., 'build_volume_y':.., 'build_volume_z':..})")
        return
    n_out = n_subzero_z = 0
    first_out = None
    for seg in segments:
        x, y, z = seg.end
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


def _check_first_layer(segments, result):
    'Warn if the first extruding move happens at or below z=0 (nozzle on/under the bed).'
    for seg in segments:
        if not seg.travel:  # first extruding move
            z = seg.end[2]
            if z is not None and z <= 0:
                result.add('warning', f'first extrusion move is at z={z} (<= 0) - nozzle may be at or below the bed')
            return


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


def _check_extrusion_geometry(segments, result):
    'Warn if the first extruding move happens with a zero/undefined extrusion cross-section.'
    for seg in segments:
        if not seg.travel:  # first extruding move
            w, h = seg.width, seg.height
            if not (w and h and w > 0 and h > 0):
                result.add('warning', 'extruding with a zero/undefined extrusion geometry '
                                      f'(width={w}, height={h}) - no material will be extruded')
            return


def _check_stringing(steps, result):
    '''Low-noise stringing heuristic: only when a design uses retraction at all, flag long
    travel moves (after printing has started) that are not preceded by a retraction.'''
    uses_retraction = any(isinstance(s, Retraction) for s in steps)
    if not uses_retraction:
        return
    extruder_on = False
    has_printed = False
    retracted = False
    tracked = Point()
    n_unretracted_travels = 0
    for step in steps:
        if isinstance(step, Retraction):
            retracted = True
        elif isinstance(step, Unretraction):
            retracted = False
        elif isinstance(step, Extruder) and step.on is not None:
            if step.on:
                retracted = False  # priming/printing resumes
            extruder_on = step.on
        elif isinstance(step, Point):
            prev = Point(x=tracked.x, y=tracked.y, z=tracked.z)
            tracked.update_from(step)
            if extruder_on:
                has_printed = True
            elif has_printed and not retracted and _xy_distance(prev, tracked) > TRAVEL_STRINGING_THRESHOLD_MM:
                n_unretracted_travels += 1
    if n_unretracted_travels:
        result.add('info', f'{n_unretracted_travels} long travel move(s) (> {TRAVEL_STRINGING_THRESHOLD_MM} mm) '
                           'without a preceding retraction - possible stringing (the design uses retraction elsewhere)')


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
