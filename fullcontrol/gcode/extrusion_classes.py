from fullcontrol.common import ExtrusionGeometry as BaseExtrusionGeometry
from fullcontrol.common import Extruder as BaseExtruder
from fullcontrol.common import StationaryExtrusion as BaseStationaryExtrusion
from fullcontrol.base import BaseModelPlus
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


class Retraction(BaseModelPlus):
    '''Retract filament to reduce oozing/stringing during a travel move.

    Emits an explicit 'G1 F<speed> E-<dist>' move. This is the explicit E-based route;
    for firmware-managed retraction use PrinterCommand(id='retract') -> G10 instead.

    Attributes:
        distance (float, optional): Filament length to retract, in the gcode E units
            (mm of filament in 'mm' mode, mm^3 in 'mm3' mode). None inherits the
            printer's default retraction distance.
        speed (float, optional): Retraction feedrate in mm/min. None inherits the
            printer's default retraction speed.
    '''
    distance: float | None = None
    speed: float | None = None


class Unretraction(BaseModelPlus):
    '''Prime filament back after a Retraction (the inverse move).

    Attributes:
        distance (float, optional): Filament length to prime, in the gcode E units.
            None primes exactly the amount currently retracted, restoring the
            cumulative extrusion position (a retract+prime nets to zero material).
        speed (float, optional): Priming feedrate in mm/min. None inherits the
            printer's default retraction speed.
    '''
    distance: float | None = None
    speed: float | None = None


class Extruder(BaseExtruder):
    '''The extruder design step: gcode-relevant design choices only (no runtime accumulators).

    Attributes:
        on (bool, optional): whether extrusion is on (inherited from the core Extruder).
        units (str, optional): the units for E in gcode - 'mm' or 'mm3'.
        dia_feed (float, optional): the diameter of the feedstock filament.
        relative_gcode (bool, optional): whether to use relative extrusion (M83) gcode.
    '''
    # design choices the user may set; options for units: 'mm' / 'mm3'
    units: str | None = None
    dia_feed: float | None = None  # diameter of the feedstock filament
    relative_gcode: bool | None = None


class ExtruderState(Extruder):
    '''The gcode backend's running extruder context: the design fields (received from each
    Extruder step via update_from) plus the emission accumulators and methods. Held by the
    gcode State (state.extruder); never appears in a design.

    Attributes:
        volume_to_e (float, optional): factor converting extruded volume (mm3) to the E value.
        total_volume (float, optional): cumulative extruded volume for the whole print.
        total_volume_ref (float, optional): reference volume, for expressing E relative to a point.
        travel_format (str, optional): the format for travel-move E ('G0' / 'G1_E0').
        retraction_distance / retraction_speed (float, optional): current retraction defaults.
        retracted_length (float, optional): filament length currently retracted.
    '''
    # calculated automatically / tracked during emission:
    volume_to_e: float | None = None
    total_volume: float | None = None
    total_volume_ref: float | None = None
    travel_format: str | None = None
    retraction_distance: float | None = None
    retraction_speed: float | None = None
    retracted_length: float | None = None

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

