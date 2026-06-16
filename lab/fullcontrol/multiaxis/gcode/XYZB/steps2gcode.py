from lab.fullcontrol.multiaxis.gcode.XYZB.state import State
from lab.fullcontrol.multiaxis.gcode.XYZB.controls import GcodeControls
from lab.fullcontrol.multiaxis.gcode._driver import run_gcode


def gcode(steps: list, gcode_controls: GcodeControls = GcodeControls()):
    'return a gcode string generated from a list of steps'
    if gcode_controls.b_offset_z is None:
        raise Exception("gcode generation requires an fc4.GcodeControls object to be supplied with the attribute 'b_offset_z' set correctly")
    return run_gcode(State(steps, gcode_controls), gcode_controls.save_as)
