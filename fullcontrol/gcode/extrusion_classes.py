from fullcontrol.common import ExtrusionGeometry as BaseExtrusionGeometry
from fullcontrol.common import Extruder as BaseExtruder
from fullcontrol.common import StationaryExtrusion as BaseStationaryExtrusion
from fullcontrol.gcode import Point
from fullcontrol.gcode.number_format import fmt
from math import pi


def _distance_forgiving(point1: Point, point2: Point) -> float:
    'Distance between two points; an axis is ignored unless defined in both points.'
    dist_x = 0 if point1.x is None or point2.x is None else point1.x - point2.x
    dist_y = 0 if point1.y is None or point2.y is None else point1.y - point2.y
    dist_z = 0 if point1.z is None or point2.z is None else point1.z - point2.z
    return (dist_x**2 + dist_y**2 + dist_z**2)**0.5


class ExtrusionGeometry(BaseExtrusionGeometry):
    'Extend generic class with the gcode-relevant area calculation'


class StationaryExtrusion(BaseStationaryExtrusion):
    'Stationary extrusion of a set volume (gcode emission handled by the renderer)'


class Extruder(BaseExtruder):
    '''
    Extend generic class with gcode methods and attributes to convert the object to gcode.

    This class is used to manage the state of the extruder and translate the design into GCode.

    Attributes:
        units (str, optional): The units for E in GCode. Options include 'mm' and 'mm3'. If not specified, a default unit is used.
        dia_feed (float, optional): The diameter of the feedstock filament.
        relative_gcode (bool, optional): A flag indicating whether to use relative GCode. If not specified, a default value is used.
        volume_to_e (float, optional): A factor to convert the volume of material into the value of 'E' in GCode. Calculated automatically.
        total_volume (float, optional): The current extrusion volume for the whole print. Calculated automatically.
        total_volume_ref (float, optional): The total extrusion volume reference value. This attribute is set to allow extrusion to be expressed relative to this point. For relative_gcode = True, it is reset for every line. Calculated automatically.
        travel_format (str, optional): The format for travel moves in the GCode. If not specified, a default format is used.
    '''

    # gcode additions to generic Extruder class

    # GCode attributes, used to translate the design into gcode:
    # units for E in GCode ... options: 'mm' / 'mm3'
    units: str | None = None
    dia_feed: float | None = None  # diameter of the feedstock filament
    relative_gcode: bool | None = None
    # attibutes not set by user ... calculated automatically:
    # factor to convert volume of material into the value of 'E' in gcode
    volume_to_e: float | None = None
    # current extrusion volume for whole print
    total_volume: float | None = None
    # total extrusion volume reference value - this attribute is set to allow extrusion to be expressed relative to this point (for relative_gcode = True, it is reset for every line)
    total_volume_ref: float | None = None
    travel_format: str | None = None

    def get_and_update_volume(self, volume):
        '''Calculate the extrusion volume and update the total volume.

        Args:
            volume (float): The volume of material to be extruded.

        Returns:
            float: The extrusion volume relative to the total volume.
        '''
        self.total_volume += volume
        ret_val = self.total_volume - self.total_volume_ref
        if self.relative_gcode is True:
            self.total_volume_ref = self.total_volume
        # to make absolute extrusion work, check self.total_volume_ref and, if above a treshold value, reset extrusion (set extruder_now.e_total_vol_reference_for_gcode = extruder_now.e_total_vol; insert a G92 command next in the steplist)
        return ret_val

    def e_gcode(self, point1: Point, state) -> str:
        '''Generate the gcode for extrusion.

        Args:
            point1 (Point): The point at the end of the extrusion.
            state: The current state of the printer.

        Returns:
            str: The gcode component for extrusion.
        '''
        if self.on:
            length = _distance_forgiving(point1, state.point)
            return f'E{fmt(self.get_and_update_volume(length*state.extrusion_geometry.area)*self.volume_to_e)}'
        else:
            if state.extruder.travel_format == 'G1_E0':
                # return 'E0' for relative extrusion or E(previous extrusion) for absolute extrusion
                return f'E{fmt(self.get_and_update_volume(0)*self.volume_to_e)}'
            else: 
                # return nothing if travel format does not require am E value
                return ''

    def update_e_ratio(self):
        '''Calculate the ratio for conversion from mm3 extrusion to units for E in gcode.'''
        try:  # try in case not all parameters set yet
            if self.units == "mm3":
                self.volume_to_e = 1
            elif self.units == "mm":
                self.volume_to_e = 1 / (pi*(self.dia_feed/2)**2)
        except TypeError:
            pass  # dia_feed not set yet (None arithmetic)

