from lab.fullcontrol.multiaxis.gcode.XYZBC.state import State
from lab.fullcontrol.multiaxis.gcode.XYZBC.controls import GcodeControls
from lab.fullcontrol.multiaxis.gcode._driver import run_gcode


def gcode(steps: list, gcode_controls: GcodeControls = GcodeControls()):
    'return a gcode string generated from a list of steps'
    return run_gcode(State(steps, gcode_controls), gcode_controls.save_as)
