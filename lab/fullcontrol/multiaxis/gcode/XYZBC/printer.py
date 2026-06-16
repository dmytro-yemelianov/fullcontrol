from fullcontrol.common import Point
from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter


class Printer(MultiaxisPrinter):
    'gcode Printer with 5-axis (B-C bed) aspects added'
    bc_intercept: Point | None = None  # point where the b and c axes intersect, in system coordinates
