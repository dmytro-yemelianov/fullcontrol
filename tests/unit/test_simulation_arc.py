"""The simulation backend must account for Arc moves (regression: Arc was silently ignored,
contributing no time/material and - worse - leaving the tracked point stale so the next move's
distance was measured from the wrong place).
"""
from math import pi

import fullcontrol as fc
from fullcontrol.simulate.result import SimulationResult


def _sim(steps):
    return fc.transform(steps, 'simulation',
                        fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                        show_tips=False)


def test_extruding_arc_contributes_time_material_and_a_segment():
    # quarter circle, radius 20 -> arc length = 20*pi/2
    r = _sim([fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
              fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise')])
    assert isinstance(r, SimulationResult)
    arc_len = 20 * pi / 2
    assert abs(r.extruding_distance - arc_len) < 1e-6
    assert r.extruded_volume > 0
    assert r.print_time_s > 0
    assert r.segment_count == 1


def test_travel_arc_counts_as_travel_not_print():
    r = _sim([fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=False),
              fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise')])
    assert r.travel_distance > 0
    assert r.print_time_s == 0.0
    assert r.extruded_volume == 0.0


def test_move_after_arc_measures_from_arc_end_not_stale_point():
    # arc ends at (0,20); the following extruding move to (0,30) is 10 mm, not measured from (20,0)
    with_arc = _sim([fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
                     fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
                     fc.Point(x=0, y=30, z=0.2)])
    arc_len = 20 * pi / 2
    # total extruding distance = arc + the straight 10 mm leg from the arc end
    assert abs(with_arc.extruding_distance - (arc_len + 10)) < 1e-6
    assert with_arc.segment_count == 2
