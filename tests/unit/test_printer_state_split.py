"""The Printer *step* carries only design data; the gcode backend's running printer context
(the resolved command_list, the speed_changed flag) and the f_gcode emission helper live on a
separate PrinterState - mirroring the Extruder / ExtruderState split.
"""
import fullcontrol as fc
from fullcontrol.gcode.printer import Printer, PrinterState

_RUNTIME = {'command_list', 'speed_changed'}
_DESIGN = {'print_speed', 'travel_speed', 'new_command'}


def test_step_printer_is_design_only():
    fields = set(Printer.model_fields)
    assert _DESIGN <= fields
    assert not (_RUNTIME & fields), f'runtime fields leaked onto the step: {_RUNTIME & fields}'
    assert not hasattr(Printer, 'f_gcode')


def test_printer_state_holds_runtime_and_f_gcode():
    fields = set(PrinterState.model_fields)
    assert _RUNTIME <= fields
    assert _DESIGN <= fields  # inherits the design fields (received via update_from)
    assert hasattr(PrinterState, 'f_gcode')


def test_combined_printer_no_longer_exposes_runtime():
    assert not (_RUNTIME & set(fc.Printer.model_fields))


def test_new_command_still_registers_and_runs():
    g = fc.transform([fc.Printer(new_command={'beep': 'M300 ; beep'}),
                      fc.PrinterCommand(id='beep'),
                      fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
                     'gcode', fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert 'M300 ; beep' in g


def test_speed_change_still_emits_feedrate():
    g = fc.transform([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                      fc.Printer(print_speed=500), fc.Point(x=10, y=0, z=0.2)],
                     'gcode', fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert 'F500' in g
