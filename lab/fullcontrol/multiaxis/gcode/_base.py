"""Shared gcode building blocks for the multiaxis backends (XYZB/XYZBC/XYZC0B1),
which otherwise differ only in their axis-rotation offset fields and kinematics."""
from fullcontrol.common import Printer as BasePrinter
from fullcontrol.gcode.number_format import fmt


class MultiaxisPrinter(BasePrinter):
    'gcode Printer behaviour shared by the multiaxis backends; axis offsets are added per variant'
    command_list: dict | None = None
    new_command: dict | None = None
    speed_changed: bool | None = None

    def f_gcode(self, state):
        if self.speed_changed is True:
            return f'F{fmt(self.print_speed if state.extruder.on else self.travel_speed, dp=1)} '
        return ''
