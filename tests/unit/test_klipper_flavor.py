"""Klipper gcode flavor. Klipper accepts the standard M-codes for temps/fan/extrusion-mode/
acceleration (so those are inherited from the Marlin default), but uses extended commands for
pressure advance (SET_PRESSURE_ADVANCE) and has no jerk - the closest analogue is
SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY.
"""
import fullcontrol as fc
from fullcontrol.gcode.flavor import get_flavor


def _gcode(steps, flavor):
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic',
                                         initialization_data={'nozzle_temp': 210, 'gcode_flavor': flavor}),
                        show_tips=False)


def test_klipper_is_registered():
    f = get_flavor('klipper')
    assert f.name == 'klipper'


def test_klipper_inherits_standard_marlin_commands():
    f = get_flavor('klipper')
    assert f.hotend_temp(210, wait=True, tool=None) == 'M109 S210 ; set hotend temp and wait'
    assert f.bed_temp(60, wait=False) == 'M140 S60 ; set bed temp and continue'
    assert f.fan(100) == 'M106 S255 ; set fan speed'
    assert f.extrusion_mode(relative=True) == 'M83 ; relative extrusion'
    assert f.acceleration(printing=500, retract=None, travel=1000) == 'M204 P500 T1000 ; set acceleration'


def test_klipper_pressure_advance_uses_set_pressure_advance():
    f = get_flavor('klipper')
    assert f.pressure_advance(0.05, tool=None) == 'SET_PRESSURE_ADVANCE ADVANCE=0.05'
    assert f.pressure_advance(None, tool=None) is None


def test_klipper_pressure_advance_tool_maps_to_extruder_name():
    f = get_flavor('klipper')
    assert f.pressure_advance(0.04, tool=0) == 'SET_PRESSURE_ADVANCE ADVANCE=0.04 EXTRUDER=extruder'
    assert f.pressure_advance(0.04, tool=1) == 'SET_PRESSURE_ADVANCE ADVANCE=0.04 EXTRUDER=extruder1'


def test_klipper_jerk_maps_to_square_corner_velocity():
    f = get_flavor('klipper')
    assert f.jerk(x=8, y=8, z=None, e=None) == 'SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=8'
    assert f.jerk(x=5, y=None, z=None, e=None) == 'SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=5'


def test_klipper_jerk_without_xy_emits_nothing():
    f = get_flavor('klipper')
    assert f.jerk(x=None, y=None, z=0.4, e=5) is None
    assert f.jerk(x=None, y=None, z=None, e=None) is None


def test_klipper_full_design_uses_extended_commands():
    g = _gcode([fc.PressureAdvance(value=0.05), fc.Jerk(x=7, y=7),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
               'klipper')
    assert 'SET_PRESSURE_ADVANCE ADVANCE=0.05' in g
    assert 'SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=7' in g
    assert 'M900' not in g and 'M205' not in g
    # inherited standard commands still appear
    assert 'M109 S210' in g
