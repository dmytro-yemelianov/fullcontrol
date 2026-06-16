"""The gcode-flavor seam: firmware-specific M-code vocabulary lives in a GcodeFlavor object
that renderers delegate to, so a design can target different firmwares. The default is
Marlin (byte-identical to before the seam existed); flavors are selectable via config.
"""
import pytest

import fullcontrol as fc
from fullcontrol.gcode.flavor import GcodeFlavor, get_flavor, register_flavor


def _gcode(steps, init=None):
    init = {'nozzle_temp': 210, **(init or {})}
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def test_default_flavor_is_marlin():
    f = get_flavor('marlin')
    assert isinstance(f, GcodeFlavor)
    assert f.name == 'marlin'


def test_unknown_flavor_raises():
    with pytest.raises(ValueError, match='flavor'):
        get_flavor('no_such_firmware')


def test_marlin_aux_commands_are_unchanged():
    f = get_flavor('marlin')
    assert f.hotend_temp(210, wait=True, tool=None) == 'M109 S210 ; set hotend temp and wait'
    assert f.hotend_temp(210, wait=False, tool=None) == 'M104 S210 ; set hotend temp and continue'
    assert f.bed_temp(60, wait=True) == 'M190 S60 ; set bed temp and wait'
    assert f.fan(100) == 'M106 S255 ; set fan speed'   # 100% -> 255 PWM
    assert f.fan(50) == 'M106 S127 ; set fan speed'    # int(50*255/100)
    assert f.extrusion_mode(relative=True) == 'M83 ; relative extrusion'
    assert f.acceleration(printing=500, retract=None, travel=1000) == 'M204 P500 T1000 ; set acceleration'


def test_selecting_a_custom_flavor_changes_emitted_gcode():
    class LoudFan(GcodeFlavor):
        name = 'loudfan'

        def fan(self, speed_percent):
            return f'M106 S{int(speed_percent)} ; CUSTOM fan'

    register_flavor('loudfan', LoudFan)
    g = _gcode([fc.Fan(speed_percent=80), fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2)], {'gcode_flavor': 'loudfan'})
    assert 'M106 S80 ; CUSTOM fan' in g
    # a different command still comes from the Marlin-style default behaviour inherited by the subclass
    assert 'M109 S210' in g


def test_default_design_uses_marlin_output():
    g = _gcode([fc.Fan(speed_percent=100), fc.Buildplate(temp=60, wait=True),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'M106 S255 ; set fan speed' in g
    assert 'M190 S60 ; set bed temp and wait' in g
