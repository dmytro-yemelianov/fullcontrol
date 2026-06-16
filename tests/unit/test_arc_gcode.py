"""Native arc moves (fc.Arc -> a single G2/G3) in the gcode backend.

The start of the arc is the current nozzle position; centre and end are absolute. The
renderer emits one G2 (clockwise) / G3 (anticlockwise) move with I/J centre offsets and an
E value computed from the true arc length (not the chord), so extrusion is correct.
"""
import re
from math import pi

import pytest

import fullcontrol as fc

# generic printer extrusion: rectangle 0.4 x 0.2 -> area 0.08 mm^2; units 'mm', dia_feed 1.75
_AREA = 0.4 * 0.2
_VOLUME_TO_E = 1 / (pi * (1.75 / 2) ** 2)


def _gcode(steps, init=None):
    init = {'nozzle_temp': 210, **(init or {})}
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _arc_line(gcode):
    lines = [ln for ln in gcode.splitlines() if ln.startswith(('G2 ', 'G3 '))]
    assert len(lines) == 1, f'expected exactly one arc line, got {lines}'
    return lines[0]


def _word(line, letter):
    m = re.search(rf'{letter}(-?\d+(?:\.\d+)?)', line)
    return float(m.group(1)) if m else None


# quarter circle: start (10,0), centre (0,0), end (0,10)
def _quarter(direction):
    return [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
            fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction=direction)]


def test_anticlockwise_emits_g3_clockwise_emits_g2():
    assert _arc_line(_gcode(_quarter('anticlockwise'))).startswith('G3 ')
    assert _arc_line(_gcode(_quarter('clockwise'))).startswith('G2 ')


def test_ij_offsets_are_centre_minus_start():
    line = _arc_line(_gcode(_quarter('anticlockwise')))
    assert _word(line, 'I') == -10  # 0 - 10
    assert _word(line, 'J') == 0    # 0 - 0


def test_end_xy_is_emitted():
    line = _arc_line(_gcode(_quarter('anticlockwise')))
    assert _word(line, 'X') == 0
    assert _word(line, 'Y') == 10


def test_extrusion_uses_true_arc_length():
    # anticlockwise quarter circle: arc length = r * pi/2 = 10 * pi/2
    line = _arc_line(_gcode(_quarter('anticlockwise')))
    expected_e = (10 * pi / 2) * _AREA * _VOLUME_TO_E
    assert abs(_word(line, 'E') - expected_e) < 1e-4


def test_clockwise_takes_the_long_way_round():
    # from (10,0) to (0,10): anticlockwise sweeps 90 deg, clockwise sweeps 270 deg
    e_ccw = _word(_arc_line(_gcode(_quarter('anticlockwise'))), 'E')
    e_cw = _word(_arc_line(_gcode(_quarter('clockwise'))), 'E')
    assert abs(e_cw / e_ccw - 3.0) < 1e-3  # 270 / 90 = 3


def test_full_circle_when_end_equals_start():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=10, y=0), direction='anticlockwise')]
    line = _arc_line(_gcode(steps))
    expected_e = (2 * pi * 10) * _AREA * _VOLUME_TO_E
    assert abs(_word(line, 'E') - expected_e) < 1e-3


def test_helical_arc_emits_z_and_includes_it_in_length():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10, z=1.2), direction='anticlockwise')]
    line = _arc_line(_gcode(steps))
    assert _word(line, 'Z') == 1.2
    planar = 10 * pi / 2
    helical_len = (planar ** 2 + (1.2 - 0.2) ** 2) ** 0.5
    expected_e = helical_len * _AREA * _VOLUME_TO_E
    assert abs(_word(line, 'E') - expected_e) < 1e-4


def test_travel_arc_has_no_e():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=False),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise')]
    line = _arc_line(_gcode(steps))
    assert 'E' not in line


def test_end_not_on_circle_raises():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=15), direction='anticlockwise')]
    with pytest.raises(ValueError, match='not on the arc'):
        _gcode(steps)


def test_arc_without_a_start_position_raises_clearly():
    # no current x/y to sweep from -> clear message (the gcode path is also guarded earlier
    # by the primer's first_point check; this guards the renderers directly)
    from fullcontrol.core.arc import arc_geometry
    arc = fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise')
    with pytest.raises(ValueError, match='start position'):
        arc_geometry(arc, None, None, None)


def test_unknown_direction_raises():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='sideways')]
    with pytest.raises(ValueError, match='direction'):
        _gcode(steps)


def test_arc_updates_current_point_for_following_move():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise'),
             fc.Point(x=0, y=20, z=0.2)]
    g = _gcode(steps)
    # the move after the arc should travel from (0,10) -> (0,20): only Y changes, no X word
    after = g.splitlines()[g.splitlines().index(_arc_line(g)) + 1]
    assert 'Y20' in after and 'X' not in after
