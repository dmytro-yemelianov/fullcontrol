from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter, MultiaxisPrinterState


class Printer(MultiaxisPrinter):
    'gcode Printer with 4-axis (B) aspects added (the design step)'
    # offsets of the axis-of-rotation relative to the nozzle when B=0 (see controls.py)
    b_offset_x: float | None = None
    b_offset_z: float | None = None


class PrinterState(MultiaxisPrinterState, Printer):
    'the running 4-axis (B) printer context: design offsets plus runtime fields/methods'
    pass
