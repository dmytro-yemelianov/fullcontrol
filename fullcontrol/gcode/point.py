from fullcontrol.common import Point as BasePoint


class Point(BasePoint):
    'gcode Point (XYZ emission handled by the renderer, which dispatches on the core Point base)'
