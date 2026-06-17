from fullcontrol.common import Printer as BasePrinter
from fullcontrol.gcode.number_format import fmt


class Printer(BasePrinter):
    '''The printer design step: print/travel speed (inherited) plus the option to register a
    new printer command. Runtime context lives on PrinterState (held by the gcode State).

    Attributes:
        new_command (Optional[dict]): a command to add to the printer's command list,
            e.g. {'my_id': 'G... ; ...'}, later emitted via PrinterCommand(id='my_id').
    '''
    new_command: dict | None = None


class PrinterState(Printer):
    '''The gcode backend's running printer context: the design fields (received from each
    Printer step via update_from) plus the resolved command list, the speed-changed flag, and
    the feedrate (F) emission helper. Held by the gcode State (state.printer).

    Attributes:
        command_list (Optional[dict]): the printer's resolved id -> gcode command map.
        speed_changed (Optional[bool]): whether the print/travel speed changed since the last move.
    '''
    command_list: dict | None = None
    speed_changed: bool | None = None

    def f_gcode(self, state):
        '''Generate the feedrate (F) word, emitted only when the speed has changed.'''
        if self.speed_changed is True:
            return f'F{fmt(self.print_speed if state.extruder.on else self.travel_speed, dp=1)} '
        return ''
