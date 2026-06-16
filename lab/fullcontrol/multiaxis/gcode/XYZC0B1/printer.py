from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter


class Printer(MultiaxisPrinter):
    'gcode Printer with 5-axis (B nozzle + C bed) aspects added'
    # offsets of the axes-of-rotation relative to the nozzle when B=0 (see controls.py)
    b_offset_x: float | None = None
    b_offset_z: float | None = None
    c_offset_x: float | None = None
    c_offset_y: float | None = None
