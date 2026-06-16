
import os
from fullcontrol.gcode.point import Point
from fullcontrol.gcode.printer import Printer
from fullcontrol.gcode.extrusion_classes import ExtrusionGeometry, Extruder
from fullcontrol.gcode.state import State
from fullcontrol.gcode.controls import GcodeControls
from datetime import datetime
from fullcontrol.gcode.tips import tips


def gcode(steps: list, gcode_controls: GcodeControls, show_tips: bool):
    '''
    Generate a gcode string from a list of steps.

    Args:
        steps (list): A list of step objects.
        gcode_controls (GcodeControls, optional): An instance of GcodeControls class. Defaults to GcodeControls().

    Returns:
        str: The generated gcode string.
    '''
    gcode_controls.initialize()
    if show_tips: tips(gcode_controls)

    state = State(steps, gcode_controls)
    # need a while loop because some classes may change the length of state.steps
    # max_iterations is a backstop against a step that endlessly appends to state.steps
    max_iterations = len(state.steps) * 1000 + 1_000_000
    while state.i < len(state.steps):
        step = state.steps[state.i]
        # call the gcode function of each class instance in 'steps'
        try:
            gcode_line = step.gcode(state)
        except Exception as e:
            raise type(e)(f'error generating gcode for step {state.i} ({type(step).__name__}): {e}') from e
        if gcode_line is not None:
            state.gcode.append(gcode_line)
        state.i += 1
        if state.i > max_iterations:
            raise RuntimeError(f'gcode generation exceeded {max_iterations} steps - a step is likely appending to the step list without terminating')
    gc = '\n'.join(state.gcode)

    if gcode_controls.save_as is not None:
        filename = gcode_controls.save_as
        filename += datetime.now().strftime("__%d-%m-%Y__%H-%M-%S.gcode") if gcode_controls.include_date is True else '.gcode'
        with open(filename, 'w') as f:
            f.write(gc)

    return gc
