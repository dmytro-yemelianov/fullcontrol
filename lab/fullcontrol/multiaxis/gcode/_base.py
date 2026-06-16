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

    def gcode(self, state):
        'process this instance in a list of steps to generate and return a line of gcode'
        # update all attributes of the tracking instance with the new instance (self)
        state.printer.update_from(self)
        if self.print_speed is not None or self.travel_speed is not None:
            state.printer.speed_changed = True
        if self.new_command is not None:
            state.printer.command_list = {**(state.printer.command_list or {}), **self.new_command}
