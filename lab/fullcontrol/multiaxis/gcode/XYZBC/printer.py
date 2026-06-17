from fullcontrol.common import Point
from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter, MultiaxisPrinterState


class Printer(MultiaxisPrinter):
    'gcode Printer with 5-axis (B-C bed) aspects added (the design step)'
    bc_intercept: Point | None = None  # point where the b and c axes intersect, in system coordinates


class PrinterState(MultiaxisPrinterState, Printer):
    'the running 5-axis (B-C bed) printer context: design offsets plus runtime fields/methods'
    pass
