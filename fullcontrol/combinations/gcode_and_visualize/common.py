
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


register_backend('gcode', GcodeControls, _run_gcode)
register_backend('plot', PlotControls, _run_plot)


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
    return runner(steps, controls, show_tips)
