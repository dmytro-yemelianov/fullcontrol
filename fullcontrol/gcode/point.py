from fullcontrol.common import Point as BasePoint
from fullcontrol.gcode.number_format import fmt


class Point(BasePoint):
    'Extend generic class with gcode methods to convert the object to gcode'

    def XYZ_gcode(self, p) -> str:
        '''
        Generate XYZ gcode string to move from a point p to this point.

        Args:
            p (Point): The point to move from.

        Returns:
            str: The XYZ gcode string.

        '''
        s = ''
        if self.x is not None and self.x != p.x:
            s += f'X{fmt(self.x)} '
        if self.y is not None and self.y != p.y:
            s += f'Y{fmt(self.y)} '
        if self.z is not None and self.z != p.z:
            s += f'Z{fmt(self.z)} '
        return s if s != '' else None
