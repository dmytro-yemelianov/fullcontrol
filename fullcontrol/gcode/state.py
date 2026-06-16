from pydantic import BaseModel, ConfigDict, Field
from importlib import import_module

from fullcontrol.gcode.point import Point
from fullcontrol.gcode.printer import Printer
from fullcontrol.gcode.extrusion_classes import ExtrusionGeometry, Extruder
from fullcontrol.gcode.controls import GcodeControls
from fullcontrol.gcode.flavor import GcodeFlavor, get_flavor
from fullcontrol.common import first_point
from fullcontrol.gcode.import_printer import resolve_initialization_data


class State(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # the flavor is a plain class
    '''
    This class tracks the state of instances of interest adjusted in the list 
    of steps (points, extruder, etc.). It also includes some relevant shared variables and 
    initialization methods. Upon instantiation, a list of steps and GcodeControls must be passed
    to allow initialization of various attributes.

    Attributes:
        extruder (Optional[Extruder]): The extruder instance.
        printer (Optional[Printer]): The printer instance.
        extrusion_geometry (Optional[ExtrusionGeometry]): The extrusion geometry instance.
        steps (Optional[list]): The list of steps.
        point (Optional[Point]): The current point.
        i (Optional[int]): The current index.
        gcode (Optional[list]): The list of Gcode.

    Methods:
        __init__: Initializes the State object.

    '''

    extruder: Extruder | None = None
    printer: Printer | None = None
    extrusion_geometry: ExtrusionGeometry | None = None
    flavor: GcodeFlavor | None = None
    steps: list | None = None
    point: Point | None = Field(default_factory=Point)
    i: int | None = 0
    gcode: list | None = Field(default_factory=list)

    def __init__(self, steps: list, gcode_controls: GcodeControls):
        """
        Initializes a State object.

        Args:
            steps (list): A list of steps for the state.
            gcode_controls (GcodeControls): An instance of the GcodeControls class.

        Returns:
            None
        """
        super().__init__()
        # resolve the named printer's default initialization_data, merged with the
        # designer's overrides from gcode_controls (dispatches Cura/Community/singletool).
        # note: with 'no_primer' there is a risk that no initial Point is defined before
        # the first G1 command, making length calculation for that line impossible.
        initialization_data = resolve_initialization_data(
            gcode_controls.printer_name, gcode_controls.initialization_data)

        self.flavor = get_flavor(initialization_data.get('gcode_flavor', 'marlin'))

        self.extruder = Extruder(
            units=initialization_data['e_units'],
            dia_feed=initialization_data['dia_feed'],
            total_volume=0,
            total_volume_ref=0,
            retraction_distance=initialization_data['retraction_distance'],
            retraction_speed=initialization_data['retraction_speed'],
            retracted_length=0,
            travel_format=initialization_data['travel_format'])
        self.extruder.update_e_ratio()
        if initialization_data['manual_e_ratio'] is not None:
            self.extruder.volume_to_e = initialization_data['manual_e_ratio']

        self.printer = Printer(
            command_list=initialization_data['printer_command_list'],
            print_speed=initialization_data['print_speed'],
            travel_speed=initialization_data['travel_speed'],
            speed_changed=True)

        self.extrusion_geometry = ExtrusionGeometry(
            area_model=initialization_data['area_model'],
            width=initialization_data['extrusion_width'],
            height=initialization_data['extrusion_height'])
        self.extrusion_geometry.update_area()

        primer_steps = import_module(f'fullcontrol.gcode.primer_library.{initialization_data["primer"]}').primer(first_point(steps))
        self.steps = initialization_data['starting_procedure_steps'] + primer_steps + steps + initialization_data['ending_procedure_steps']
