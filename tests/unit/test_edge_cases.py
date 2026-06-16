"""Edge-case / regression coverage for the features added this cycle (arcs, retraction,
gcode flavors, validation). Characterises behaviour that is easy to break later.
"""
import re

import pytest

import fullcontrol as fc


def _gcode(steps, init=None):
    init = {'nozzle_temp': 210, **(init or {})}
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _word(line, letter):
    m = re.search(rf'{letter}(-?\d+(?:\.\d+)?)', line)
    return float(m.group(1)) if m else None


def _arc_line(g):
    return next(ln for ln in g.splitlines() if ln.startswith(('G2 ', 'G3 ')))


# --- arcs ---

def test_arc_default_direction_is_clockwise():
    g = _gcode([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
                fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10))])
    assert _arc_line(g).startswith('G2 ')


def test_semicircle_arc_length_is_twice_the_quarter():
    quarter = _gcode([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
                      fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10), direction='anticlockwise')])
    semi = _gcode([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
                   fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=-10, y=0), direction='anticlockwise')])
    assert abs(_word(_arc_line(semi), 'E') / _word(_arc_line(quarter), 'E') - 2.0) < 1e-3


def test_arc_off_origin_centre_offsets_are_relative_to_start():
    # start (15,5), centre (5,5) -> I = 5-15 = -10, J = 5-5 = 0
    g = _gcode([fc.Point(x=15, y=5, z=0.2), fc.Extruder(on=True),
                fc.Arc(centre=fc.Point(x=5, y=5), end=fc.Point(x=5, y=15), direction='anticlockwise')])
    line = _arc_line(g)
    assert _word(line, 'I') == -10 and _word(line, 'J') == 0


def test_arc_segments_control_visualization_density():
    pd = fc.transform([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
                       fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10),
                              direction='anticlockwise', segments=8)],
                      'plot', fc.PlotControls(raw_data=True, printer_name='generic'), show_tips=False)
    assert len(pd.paths[-1].xvals) == 9  # 1 start + 8 segments


# --- retraction ---

def test_over_prime_floors_retracted_length_at_zero():
    # retract 2, then prime an explicit 5 -> emits E5 but does not leave a negative retracted state
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
                fc.Retraction(distance=2), fc.Point(x=10, y=10, z=0.2),
                fc.Unretraction(distance=5), fc.Point(x=0, y=10, z=0.2),
                fc.Unretraction()])  # nothing left retracted -> this one emits nothing
    unretracts = [ln for ln in g.splitlines() if 'unretract' in ln]
    assert len(unretracts) == 1 and 'E5' in unretracts[0]


def test_multiple_retractions_accumulate_then_prime_together():
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
                fc.Retraction(distance=1), fc.Retraction(distance=2),
                fc.Point(x=10, y=10, z=0.2), fc.Unretraction()])  # primes the accumulated 3
    unretract = next(ln for ln in g.splitlines() if 'unretract' in ln)
    assert _word(unretract, 'E') == 3


def test_zero_distance_retraction_emits_nothing():
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
                fc.Retraction(distance=0)])
    assert 'retract' not in g


# --- gcode flavors ---

def test_unknown_flavor_selection_raises_clearly():
    with pytest.raises(ValueError, match='flavor'):
        _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
               {'gcode_flavor': 'nonexistent_firmware'})


def test_marlin_multitool_hotend_path():
    g = _gcode([fc.Hotend(temp=215, wait=False, tool=1), fc.Point(x=0, y=0, z=0.2),
                fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'M104 S215 T1' in g


# --- validation ---

def test_validate_clean_design_is_ok():
    r = fc.transform([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=50, z=0.2)],
                     'validate',
                     fc.GcodeControls(printer_name='generic',
                                      initialization_data={'nozzle_temp': 210, 'build_volume_x': 200,
                                                            'build_volume_y': 200, 'build_volume_z': 200}),
                     show_tips=False)
    assert r.ok


def test_validate_does_not_consume_or_mutate_the_design():
    steps = [fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=50, z=0.2)]
    before = len(steps)
    fc.transform(steps, 'validate', fc.GcodeControls(printer_name='generic',
                 initialization_data={'nozzle_temp': 210}), show_tips=False)
    # transform fixes a copy; the user's list is unchanged and gcode still generates afterwards
    assert len(steps) == before
    assert 'G1' in _gcode(steps)


# --- tuning step objects ---

def test_empty_tuning_objects_emit_no_line():
    g = _gcode([fc.Acceleration(), fc.Jerk(), fc.PressureAdvance(),
                fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'M204' not in g and 'M205' not in g and 'M900' not in g
