"""Pre-flight validation of a design (run via transform(steps, 'validate', controls)).

A fast, best-effort safety pass over the resolved gcode step list: out-of-bounds points,
sub-zero Z, and likely cold extrusion. It reuses the gcode State so it sees the real
coordinates (including the printer's start/end procedures and primer).
"""
import numpy as np

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


def _reported(v):
    'A column scalar for a message: NaN (undefined axis/geometry) -> None, else a plain float.'
    return None if np.isnan(v) else float(v)


def validate(steps, controls, show_tips=True) -> ValidationResult:
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.import_printer import resolve_initialization_data
    from fullcontrol.ir.columnar import resolve_columnar
    controls.initialize()
    init = resolve_initialization_data(controls.printer_name, controls.initialization_data)
    state = State(steps, controls)
    # geometric checks fold over the resolved Toolpath as numpy columns (one shared columnar
    # resolve, reusing the State just built - no per-Segment objects); config / ordering checks
    # still walk the resolved step list
    col = resolve_columnar(steps, controls, state=state)
    result = ValidationResult()
    _validate_columnar_and_steps(col, state.steps, init, result)
    return result


def _validate_columnar_and_steps(col, steps, init, result, check_geometry=True):
    '''Run the 8 validation rules given an already-built columnar view and step list.

    Extracted so the g-code verification engine can reuse the exact same rules over a g-code that
    was parsed back into a Toolpath, without re-resolving from a design's steps. `col` is a
    `ColumnarToolpath`; `steps` is the resolved step/event list (for config/ordering checks - on a
    parsed external g-code many of these arrive as pass-through `ManualGcode` and so naturally
    no-op). The public `validate(steps, controls)` is unchanged - it still builds State internally
    and calls this with the State's columnar + resolved step list.'''
    _check_bounds(col, init, result)
    _check_first_layer(col, result)
    if check_geometry:
        _check_extrusion_geometry(col, result)
    _check_cold_extrusion(steps, init, result)
    _check_temperatures(steps, result)
    _check_speeds(steps, init, result)
    _check_retraction_balance(steps, init, result)
    _check_stringing(steps, result)


def validate_toolpath(toolpath, init, result) -> ValidationResult:
    '''Run the existing validation rules over an already-parsed `Toolpath` (the inner reusable
    entry point for the g-code verification engine).

    `toolpath` is an object `Toolpath` (e.g. from `parse_gcode`); `init` is a
    resolved-initialization-data dict (build volume, speeds, retraction default, start_gcode...);
    `result` is the `ValidationResult` to append to. Geometric checks fold over a columnar view of
    the toolpath; config/ordering checks walk `toolpath.events`.'''
    from fullcontrol.ir.columnar import ColumnarToolpath
    col = ColumnarToolpath.from_toolpath(toolpath)
    # the parser cannot recover width/height from E alone, so on bare external g-code every
    # segment's geometry is NaN. Skip the zero-geometry check in that case - it would otherwise
    # fire on *every* parsed g-code (a parser limitation, not a real defect). When at least one
    # segment carries geometry (from slicer ;WIDTH:/;HEIGHT: comments) the check still runs.
    check_geometry = bool(col.width.size) and not np.all(np.isnan(col.width))
    _validate_columnar_and_steps(col, toolpath.events, init, result, check_geometry=check_geometry)
    return result


def _check_bounds(col, init, result):
    'Out-of-bounds and negative-z, vectorised over the resolved move endpoints.'
    bx, by, bz = init.get('build_volume_x'), init.get('build_volume_y'), init.get('build_volume_z')
    if not (bx and by and bz):
        result.add('info', 'build volume not defined for this printer - out-of-bounds check skipped '
                           "(pass initialization_data={'build_volume_x':.., 'build_volume_y':.., 'build_volume_z':..})")
        return
    x, y, z = col.end[:, 0], col.end[:, 1], col.end[:, 2]  # NaN where an axis is undefined
    outside = ((~np.isnan(x) & ((x < 0) | (x > bx))) |
               (~np.isnan(y) & ((y < 0) | (y > by))) |
               (~np.isnan(z) & ((z < 0) | (z > bz))))
    n_out = int(outside.sum())
    n_subzero_z = int((~np.isnan(z) & (z < 0)).sum())
    if n_out:
        idx = int(np.argmax(outside))  # first offending endpoint, in move order
        result.add('error', f'{n_out} point(s) outside the build volume ({bx}x{by}x{bz}); '
                            f'first at (x={_reported(x[idx])}, y={_reported(y[idx])}, z={_reported(z[idx])})')
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


def _check_first_layer(col, result):
    'Warn if the first extruding move happens at or below z=0 (nozzle on/under the bed).'
    extruding = ~col.travel
    if not extruding.any():
        return
    idx = int(np.argmax(extruding))  # first extruding move
    z = col.end[idx, 2]
    if not np.isnan(z) and z <= 0:
        result.add('warning', f'first extrusion move is at z={_reported(z)} (<= 0) - nozzle may be at or below the bed')


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


def _check_extrusion_geometry(col, result):
    'Warn if the first extruding move happens with a zero/undefined extrusion cross-section.'
    extruding = ~col.travel
    if not extruding.any():
        return
    idx = int(np.argmax(extruding))  # first extruding move
    w, h = _reported(col.width[idx]), _reported(col.height[idx])
    if not (w and h and w > 0 and h > 0):
        result.add('warning', 'extruding with a zero/undefined extrusion geometry '
                              f'(width={w}, height={h}) - no material will be extruded')


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
