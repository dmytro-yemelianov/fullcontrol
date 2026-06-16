"""First-class Acceleration step object -> M204.

M204 (set max acceleration) is portable across Marlin / Klipper / RepRap-Duet, so it can
be a flavor-independent step object. Firmware-specific tuning (jerk M205, pressure advance)
is deferred to the gcode-flavor abstraction.
"""
import fullcontrol as fc
from fullcontrol.gcode.renderers import render_gcode


def _gcode(steps):
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                        show_tips=False)


def test_acceleration_is_exposed():
    assert hasattr(fc, 'Acceleration')


def test_acceleration_emits_m204_with_set_fields_only():
    line = render_gcode(fc.Acceleration(printing=500, travel=1000), None)
    assert line == 'M204 P500 T1000 ; set acceleration'


def test_acceleration_field_order_is_p_r_t():
    line = render_gcode(fc.Acceleration(printing=500, retract=800, travel=1000), None)
    assert line == 'M204 P500 R800 T1000 ; set acceleration'


def test_acceleration_with_no_fields_emits_nothing():
    assert render_gcode(fc.Acceleration(), None) is None


def test_acceleration_formats_without_trailing_zeros():
    line = render_gcode(fc.Acceleration(printing=500.0), None)
    assert line == 'M204 P500 ; set acceleration'


def test_acceleration_appears_in_a_full_design():
    g = _gcode([fc.Acceleration(printing=800, travel=1200),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'M204 P800 T1200 ; set acceleration' in g
