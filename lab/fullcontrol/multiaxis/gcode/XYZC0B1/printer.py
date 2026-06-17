from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter, MultiaxisPrinterState


class Printer(MultiaxisPrinter):
    'gcode Printer with 5-axis (B nozzle + C bed) aspects added (the design step)'
    # offsets of the axes-of-rotation relative to the nozzle when B=0 (see controls.py)
    b_offset_x: float | None = None
    b_offset_z: float | None = None
    c_offset_x: float | None = None
    c_offset_y: float | None = None


class PrinterState(MultiaxisPrinterState, Printer):
    'the running 5-axis (B nozzle + C bed) printer context: design offsets plus runtime fields/methods'
    pass
