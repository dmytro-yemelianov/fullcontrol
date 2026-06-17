
from fullcontrol.gcode.state import State
from fullcontrol.gcode.controls import GcodeControls
from datetime import datetime
from fullcontrol.gcode.tips import tips
from fullcontrol.gcode.dialect import gcode_from_ir
from fullcontrol.ir import resolve


def gcode(steps: list, gcode_controls: GcodeControls, show_tips: bool):
    '''
    Generate a gcode string from a list of steps.

    The design is resolved once to the shared Toolpath IR (motion/geometry/speed), then a gcode
    dialect folds that IR into lines using the running State for the gcode-specific emission
    state (E accumulator, command list, feedrate suppression, comments).

    Args:
        steps (list): A list of step objects.
        gcode_controls (GcodeControls, optional): An instance of GcodeControls class. Defaults to GcodeControls().

    Returns:
        str: The generated gcode string.
    '''
    gcode_controls.initialize()
    if show_tips: tips(gcode_controls)

    dstate = State(steps, gcode_controls)
    toolpath = resolve(steps, gcode_controls)
    gcode_from_ir(toolpath, dstate)
    gc = '\n'.join(dstate.gcode)

    if gcode_controls.save_as is not None:
        filename = gcode_controls.save_as
        filename += datetime.now().strftime("__%d-%m-%Y__%H-%M-%S.gcode") if gcode_controls.include_date is True else '.gcode'
        with open(filename, 'w') as f:
            f.write(gc)

    return gc
