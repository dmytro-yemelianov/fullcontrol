"""Duet / RepRapFirmware gcode flavor. RRF accepts the standard M-codes for temps/fan/
extrusion-mode/acceleration (so those are inherited from the Marlin default), but jerk uses
M566 in mm/min (vs FullControl's mm/s, hence x60) and pressure advance uses M572 D<drive>.
"""
import fullcontrol as fc
from fullcontrol.gcode.flavor import get_flavor


def _gcode(steps, flavor):
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic',
                                         initialization_data={'nozzle_temp': 210, 'gcode_flavor': flavor}),
                        show_tips=False)


def test_duet_is_registered():
    f = get_flavor('duet')
    assert f.name == 'duet'


def test_reprapfirmware_alias_is_registered():
    f = get_flavor('reprapfirmware')
    assert f.name == 'duet'


def test_duet_inherits_standard_marlin_commands():
    f = get_flavor('duet')
    assert f.hotend_temp(210, wait=True, tool=None) == 'M109 S210 ; set hotend temp and wait'
    assert f.bed_temp(60, wait=False) == 'M140 S60 ; set bed temp and continue'
    assert f.fan(100) == 'M106 S255 ; set fan speed'
    assert f.extrusion_mode(relative=True) == 'M83 ; relative extrusion'
    assert f.acceleration(printing=500, retract=None, travel=1000) == 'M204 P500 T1000 ; set acceleration'


def test_duet_jerk_uses_m566_with_mm_per_min_conversion():
    f = get_flavor('duet')
    # mm/s -> mm/min is x60: 10 -> 600, 0.4 -> 24
    assert f.jerk(x=10, y=10, z=0.4, e=5) == \
        'M566 X600 Y600 Z24 E300 ; set jerk (max instantaneous speed change)'
    assert f.jerk(x=8, y=None, z=None, e=None) == \
        'M566 X480 ; set jerk (max instantaneous speed change)'


def test_duet_jerk_without_any_axis_emits_nothing():
    f = get_flavor('duet')
    assert f.jerk(x=None, y=None, z=None, e=None) is None


def test_duet_pressure_advance_uses_m572():
    f = get_flavor('duet')
    assert f.pressure_advance(0.05, tool=None) == 'M572 D0 S0.05 ; set pressure advance'
    assert f.pressure_advance(None, tool=None) is None


def test_duet_pressure_advance_tool_maps_to_drive():
    f = get_flavor('duet')
    assert f.pressure_advance(0.04, tool=0) == 'M572 D0 S0.04 ; set pressure advance'
    assert f.pressure_advance(0.04, tool=1) == 'M572 D1 S0.04 ; set pressure advance'


def test_duet_full_design_emits_expected_commands():
    g = _gcode([fc.PressureAdvance(value=0.05), fc.Jerk(x=10, y=10),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
               'duet')
    assert 'M572 D0 S0.05 ; set pressure advance' in g
    assert 'M566 X600 Y600 ; set jerk (max instantaneous speed change)' in g
    assert 'M900' not in g and 'M205' not in g
    # inherited standard commands still appear
    assert 'M109 S210' in g
