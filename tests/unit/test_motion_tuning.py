"""Flavor-aware motion-tuning step objects: Jerk (Marlin M205) and PressureAdvance
(Marlin M900 K / 'linear advance'). These complete the print-tuning trio started by
Acceleration (M204); the emitted command is firmware-specific so it goes through the
gcode flavor.
"""
from types import SimpleNamespace

import fullcontrol as fc
from fullcontrol.gcode.flavor import get_flavor
from fullcontrol.gcode.renderers import render_gcode

_MARLIN = SimpleNamespace(flavor=get_flavor('marlin'))


def _gcode(steps):
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                        show_tips=False)


def test_jerk_and_pressure_advance_are_exposed():
    assert hasattr(fc, 'Jerk') and hasattr(fc, 'PressureAdvance')


def test_jerk_emits_m205_with_set_axes_only():
    assert render_gcode(fc.Jerk(x=8, y=8), _MARLIN) == 'M205 X8 Y8 ; set jerk'
    assert render_gcode(fc.Jerk(x=10, y=10, z=0.4, e=5), _MARLIN) == 'M205 X10 Y10 Z0.4 E5 ; set jerk'


def test_jerk_with_no_axes_emits_nothing():
    assert render_gcode(fc.Jerk(), _MARLIN) is None


def test_pressure_advance_emits_m900_k():
    assert render_gcode(fc.PressureAdvance(value=0.05), _MARLIN) == 'M900 K0.05 ; set pressure advance'


def test_pressure_advance_with_tool():
    assert render_gcode(fc.PressureAdvance(value=0.04, tool=1), _MARLIN) == 'M900 T1 K0.04 ; set pressure advance'


def test_pressure_advance_without_value_emits_nothing():
    assert render_gcode(fc.PressureAdvance(), _MARLIN) is None


def test_tuning_in_a_full_design():
    g = _gcode([fc.Jerk(x=7, y=7), fc.PressureAdvance(value=0.06),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'M205 X7 Y7 ; set jerk' in g
    assert 'M900 K0.06 ; set pressure advance' in g


def test_a_custom_flavor_can_change_pressure_advance():
    from fullcontrol.gcode.flavor import GcodeFlavor, register_flavor

    class Klipperish(GcodeFlavor):
        name = 'klipperish'

        def pressure_advance(self, value, tool):
            return None if value is None else f'SET_PRESSURE_ADVANCE ADVANCE={value}'

    register_flavor('klipperish', Klipperish)
    g = fc.transform([fc.PressureAdvance(value=0.05), fc.Point(x=0, y=0, z=0.2),
                      fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
                     'gcode',
                     fc.GcodeControls(printer_name='generic',
                                      initialization_data={'nozzle_temp': 210, 'gcode_flavor': 'klipperish'}),
                     show_tips=False)
    assert 'SET_PRESSURE_ADVANCE ADVANCE=0.05' in g
    assert 'M900' not in g
