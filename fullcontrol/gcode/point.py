from typing import Optional
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

    def gcode(self, state):
        '''
        Process this instance in a list of steps supplied by the designer to generate and return a line of gcode.

        Args:
            state (State): The state object containing printer and extruder information.

        Returns:
            str: The generated line of gcode.

        '''
        XYZ_str = self.XYZ_gcode(state.point)
        if XYZ_str is not None:  # only write a line of gcode if movement occurs
            G_str = 'G1 ' if state.extruder.on or state.extruder.travel_format == "G1_E0" else 'G0 '
            F_str = state.printer.f_gcode(state)
            E_str = state.extruder.e_gcode(self, state)
            gcode_str = f'{G_str}{F_str}{XYZ_str}{E_str}'
            state.printer.speed_changed = False
            state.point.update_from(self)
            return gcode_str.strip()  # strip the final space
