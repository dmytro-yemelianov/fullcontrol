"""IR -> IR optimization passes (opt-in via initialization_data['optimize'])."""
import pytest

import fullcontrol as fc
from fullcontrol.ir import available_passes, apply_passes, Toolpath, Segment
from fullcontrol.ir.passes import merge_collinear, coasting, z_hop


def _gcode(steps, optimize=None):
    init = {'nozzle_temp': 210}
    if optimize is not None:
        init['optimize'] = optimize
    return fc.transform(steps, 'gcode', fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _moves(g):
    return [ln for ln in g.splitlines() if ln.startswith(('G0', 'G1', 'G2', 'G3'))]


# --- framework ---

def test_passes_are_registered():
    assert 'merge_collinear' in available_passes()
    assert 'retract_on_travel' in available_passes()
    assert 'coasting' in available_passes()
    assert 'z_hop' in available_passes()


def test_unknown_pass_raises():
    with pytest.raises(ValueError, match='unknown optimization pass'):
        apply_passes(Toolpath([]), ['no_such_pass'])


def test_no_optimize_is_byte_identical():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=20, y=0, z=0.2)]
    assert _gcode(steps) == _gcode(steps, optimize=[])


# --- merge_collinear ---

def test_merge_collinear_reduces_collinear_moves():
    # three collinear extruding points -> two G1 moves; merged -> one
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=20, y=0, z=0.2), fc.Point(x=30, y=0, z=0.2)]
    plain = _moves(_gcode(steps))
    merged = _moves(_gcode(steps, optimize=['merge_collinear']))
    assert len(merged) < len(plain)
    # the merged move still ends at the final point
    assert any('X30' in ln for ln in merged)


def test_merge_collinear_preserves_total_extrusion():
    # the merged single move's E must equal the sum of the two it replaced (relative E)
    seg_a = Segment((0, 0, 0), (10, 0, 0), False, 1000, 10, 0.8, 0.5, 0)
    seg_b = Segment((10, 0, 0), (20, 0, 0), False, 1000, 10, 0.8, 0.5, 1)
    out = merge_collinear(Toolpath([seg_a, seg_b]))
    assert len(out.events) == 1
    m = out.events[0]
    assert m.end == (20, 0, 0)
    assert m.length == 20 and abs(m.deposited_volume - 1.6) < 1e-9 and abs(m.filament_length - 1.0) < 1e-9


def test_merge_collinear_does_not_merge_a_corner():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]  # a right-angle corner
    merged = _moves(_gcode(steps, optimize=['merge_collinear']))
    assert any('X10' in ln and 'Y' not in ln for ln in merged)   # the corner point is kept
    assert any('Y10' in ln for ln in merged)


# --- retract_on_travel ---

def test_retract_on_travel_inserts_retraction_around_travel():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=80, y=80, z=0.2),   # long travel
             fc.Extruder(on=True), fc.Point(x=80, y=70, z=0.2)]
    g = _gcode(steps, optimize=['retract_on_travel'])
    assert '; retract' in g and '; unretract' in g
    # without the pass, no retraction
    assert '; retract' not in _gcode(steps)


def test_retract_on_travel_skips_short_travels():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=10.5, y=0, z=0.2),  # 0.5 mm travel < default 2 mm
             fc.Extruder(on=True), fc.Point(x=20, y=0, z=0.2)]
    assert '; retract' not in _gcode(steps, optimize=[('retract_on_travel', {'min_distance': 2.0})])


def test_passes_compose_and_apply_to_simulation_too():
    # optimization runs for every backend; merge_collinear shouldn't change simulated material
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=20, y=0, z=0.2)]
    def sim(opt):
        init = {'nozzle_temp': 210}
        if opt is not None:
            init['optimize'] = opt
        return fc.transform(steps, 'simulation', fc.GcodeControls(printer_name='generic', initialization_data=init), show_tips=False)
    a, b = sim(None), sim(['merge_collinear'])
    assert abs(a.extruded_volume - b.extruded_volume) < 1e-9
    assert abs(a.extruding_distance - b.extruding_distance) < 1e-9


# --- coasting ---

def test_coasting_makes_end_of_run_non_extruding():
    # a 10 mm extruding line followed by a travel; coasting 1 mm -> the last move loses 1 mm of E
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=40, y=40, z=0.2)]
    plain = _moves(_gcode(steps))
    coasted = _moves(_gcode(steps, optimize=['coasting']))
    # the extruding move is shortened (now ends at X9, not X10) and a bare X10 travel appears
    assert any('X9 ' in ln and 'E' in ln for ln in coasted)
    assert any(ln.startswith('G0') and 'X10' in ln for ln in coasted)
    # the print path is split into more moves than before
    assert len(coasted) > len(plain)


def test_coasting_scales_deposited_material():
    # 10 mm extruding line ending at the design's end -> next_motion is None, so it coasts
    seg = Segment((0, 0, 0), (10, 0, 0), False, 1000, 10, 1.0, 0.6, 0)
    out = coasting(Toolpath([seg]), distance=2.0)
    assert len(out.events) == 2
    extrude, travel = out.events
    assert extrude.travel is False and extrude.end == (8.0, 0, 0) and extrude.length == 8.0
    assert abs(extrude.deposited_volume - 0.8) < 1e-9 and abs(extrude.filament_length - 0.48) < 1e-9
    assert travel.travel is True and travel.end == (10, 0, 0)
    assert travel.deposited_volume == 0.0 and travel.filament_length == 0.0


def test_coasting_skips_short_runs_and_arcs():
    short = Segment((0, 0, 0), (1, 0, 0), False, 1000, 1, 0.1, 0.05, 0)
    arc = Segment((0, 0, 0), (10, 0, 0), False, 1000, 10, 1.0, 0.6, 1, kind='arc')
    out = coasting(Toolpath([short, arc]), distance=2.0)
    assert out.events == [short, arc]   # nothing split


# --- z_hop ---

def test_z_hop_raises_travel_z():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=40, y=40, z=0.2),
             fc.Extruder(on=True), fc.Point(x=40, y=30, z=0.2)]
    hopped = _moves(_gcode(steps, optimize=[('z_hop', {'height': 0.4})]))
    # a lift to the raised Z (0.2 + 0.4) and a lower back to 0.2 both appear, as travels
    assert any(ln.startswith('G0') and 'Z0.6' in ln for ln in hopped)
    assert any(ln.startswith('G0') and 'Z0.2' in ln for ln in hopped)
    # the in-plane travel between lift and lower carries no Z change
    assert any(ln.startswith('G0') and 'X40' in ln and 'Y40' in ln and 'Z' not in ln for ln in hopped)
    # without the pass there is no raised-Z travel
    assert not any('Z0.6' in ln for ln in _moves(_gcode(steps)))


def test_z_hop_emits_three_travels_and_deposits_nothing():
    travel = Segment((0, 0, 0.2), (10, 0, 0.2), True, 8000, 10, 0.0, 0.0, 3)
    out = z_hop(Toolpath([travel]), height=0.4)
    assert len(out.events) == 3
    lift, across, lower = out.events
    assert lift.start == (0, 0, 0.2) and lift.end == pytest.approx((0, 0, 0.6))
    assert across.start == pytest.approx((0, 0, 0.6)) and across.end == pytest.approx((10, 0, 0.6))
    assert lower.start == pytest.approx((10, 0, 0.6)) and lower.end == (10, 0, 0.2)
    assert all(s.travel and s.deposited_volume == 0.0 and s.filament_length == 0.0 for s in out.events)


def test_z_hop_skips_arcs_and_positioning_moves():
    positioning = Segment((None, None, None), (0, 0, 0.2), True, 8000, 0, 0.0, 0.0, 0)
    arc = Segment((0, 0, 0.2), (10, 0, 0.2), True, 8000, 10, 0.0, 0.0, 1, kind='arc')
    out = z_hop(Toolpath([positioning, arc]), height=0.4)
    assert out.events == [positioning, arc]   # neither is hopped
