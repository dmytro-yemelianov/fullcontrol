"""The gcode flavor owns motion-line assembly (linear G0/G1 and arc G2/G3), so the move
command and format are a single overridable place - and the main and multiaxis backends share
one assembly path instead of duplicating it.
"""
import fullcontrol as fc
from fullcontrol.gcode.flavor import get_flavor, GcodeFlavor, register_flavor


def test_marlin_linear_move_assembly():
    f = get_flavor('marlin')
    assert f.linear_move(True, 'F1000 ', 'X10 ', 'E0.5') == 'G1 F1000 X10 E0.5'
    assert f.linear_move(False, 'F8000 ', 'X10 ', '') == 'G0 F8000 X10'
    # a forced-E travel (G1_E0 format gives a non-empty e_str even when not extruding) -> G1
    assert f.linear_move(False, 'F8000 ', 'X10 ', 'E0').startswith('G1 ')


def test_marlin_arc_move_assembly():
    f = get_flavor('marlin')
    assert f.arc_move(False, 'F1000 ', 'X0 Y10 ', 'I-10 J0 ', 'E0.5') == 'G3 F1000 X0 Y10 I-10 J0 E0.5'
    assert f.arc_move(True, '', 'X0 Y10 ', 'I-10 J0 ', '').startswith('G2 ')


def test_custom_flavor_can_reformat_every_move():
    class Commented(GcodeFlavor):
        name = 'commented'

        def linear_move(self, extruding, f_str, axes_str, e_str):
            return super().linear_move(extruding, f_str, axes_str, e_str) + ' ; move'

    register_flavor('commented', Commented)
    g = fc.transform([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
                     'gcode', fc.GcodeControls(printer_name='generic',
                                               initialization_data={'nozzle_temp': 210, 'gcode_flavor': 'commented'}),
                     show_tips=False)
    move_lines = [ln for ln in g.splitlines() if ln.startswith(('G0', 'G1'))]
    assert move_lines and all(ln.endswith('; move') for ln in move_lines)


def test_arc_goes_through_flavor_arc_move():
    class ArcTag(GcodeFlavor):
        name = 'arctag'

        def arc_move(self, clockwise, f_str, coords_str, ij_str, e_str):
            return super().arc_move(clockwise, f_str, coords_str, ij_str, e_str) + ' ; arc'

    register_flavor('arctag', ArcTag)
    g = fc.transform([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
                      fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise')],
                     'gcode', fc.GcodeControls(printer_name='generic',
                                               initialization_data={'nozzle_temp': 210, 'gcode_flavor': 'arctag'}),
                     show_tips=False)
    assert any(ln.startswith('G3') and ln.endswith('; arc') for ln in g.splitlines())
