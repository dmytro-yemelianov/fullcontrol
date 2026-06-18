
from typing import Union

# see comment in __init__.py about why this module exists

# import functions and classes that will be accessible to the user
from .classes import *
from .backends import register_backend, get_backend, available_backends
from fullcontrol.common import fix
from fullcontrol.common import check, flatten, linspace, export_design, import_design, points_only, relative_point, first_point, last_point
from fullcontrol.geometry import *
from fullcontrol.visualize.bounding_box import BoundingBox


def _run_gcode(steps, controls, show_tips):
    from fullcontrol.gcode.steps2gcode import gcode
    return gcode(steps, controls, show_tips)


def _run_plot(steps, controls, show_tips):
    from fullcontrol.visualize.steps2visualization import visualize
    return visualize(steps, controls, show_tips)


def _run_simulation(steps, controls, show_tips):
    from fullcontrol.simulate.run import simulate
    return simulate(steps, controls, show_tips)


def _run_validate(steps, controls, show_tips):
    from fullcontrol.validate.run import validate
    return validate(steps, controls, show_tips)


def _run_3d_html(steps, controls, show_tips):
    from fullcontrol.visualize.threejs import export_html
    return export_html(steps, controls, show_tips)


register_backend('gcode', GcodeControls, _run_gcode)
register_backend('simulation', GcodeControls, _run_simulation)
register_backend('validate', GcodeControls, _run_validate)
register_backend('plot', PlotControls, _run_plot)
register_backend('3d_html', PlotControls, _run_3d_html)


def transform(steps: list, result_type: str, controls: GcodeControls | PlotControls = None, show_tips: bool = True):
    '''
    Transform a fullcontrol design (a list of class instances) into the specified result_type.

    Parameters:
        - steps (list): A list of function class instances representing the fullcontrol design.
        - result_type (str): The desired result type (a registered backend). Built-in
          options are "gcode" and "plot"; see available_backends().
        - controls (Union[GcodeControls, PlotControls], optional): Controls to customize
          generation. Defaults to the backend's controls class.

    Returns:
        - The transformed result for the specified result_type.

    Example usage:
        transform(steps, "gcode", controls)
    '''
    controls_class, runner = get_backend(result_type)
    if controls is None:
        controls = controls_class()
    steps = fix(steps, result_type, controls)
    _self_verify(steps, controls)
    return runner(steps, controls, show_tips)


def _self_verify(steps, controls):
    '''Opt-in pre-flight: if `initialization_data` declares `invariants`, resolve the design once and
    check them (the IR-level fullcontrol.ir.check_invariants), so every backend's output is guarded.
    `invariant_mode` (default 'raise') -> raise on violation; 'warn' -> print and continue. Off by
    default (no `invariants` key -> no-op), so existing output is unchanged.'''
    init_data = getattr(controls, 'initialization_data', None) or {}
    names = init_data.get('invariants')
    if not names:
        return
    from fullcontrol.ir import resolve, check_invariants
    toolpath = resolve(steps, controls)
    build_volume = None
    try:
        from fullcontrol.gcode.import_printer import resolve_initialization_data
        init = resolve_initialization_data(getattr(controls, 'printer_name', None), init_data)
        bx, by, bz = (init.get('build_volume_x'), init.get('build_volume_y'),
                      init.get('build_volume_z'))
        if None not in (bx, by, bz):
            build_volume = (bx, by, bz)
    except Exception:
        pass                                   # build-volume optional; within_build_volume just skips
    report = check_invariants(toolpath, names, build_volume=build_volume,
                              max_flow=init_data.get('max_flow'))
    if init_data.get('invariant_mode', 'raise') == 'warn':
        if not report.ok:
            print(f'invariant warning(s):\n{report.summary()}')
    else:
        report.raise_if_violated()
