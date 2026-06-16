from fullcontrol.common import Printer as BasePrinter
from fullcontrol.gcode.number_format import fmt
# from fullcontrol.common import MultitoolPrinter as BaseMultitoolPrinter


class Printer(BasePrinter):
    '''
    Extend generic class with gcode methods and attributes to convert the object to gcode

    Additional Attributes:
        command_list (Optional[dict]): A dictionary containing the printer's command list.
        new_command (Optional[dict]): A dictionary containing a new command to be added to the command list.
        speed_changed (Optional[bool]): A flag indicating whether the print speed or travel speed has changed.
    '''
    command_list: dict | None = None
    new_command: dict | None = None
    speed_changed: bool | None = None

    def f_gcode(self, state):
        """
        Generate the G-code for the feedrate (F) based on the current state.

        Parameters:
        - state: The current state of the printer.

        Returns:
        - The G-code string for the feedrate (F) based on the current state.
        """
        if self.speed_changed is True:
            return f'F{fmt(self.print_speed if state.extruder.on else self.travel_speed, dp=1)} '
        else:
            return ''

