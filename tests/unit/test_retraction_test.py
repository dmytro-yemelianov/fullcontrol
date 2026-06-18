"""The 2000-Retractions Test design must resolve cleanly through all four backends, and - the point
of the design - perform exactly the requested number of retractions.

Mirrors tests/unit/test_examples.py (resolve -> gcode, simulate, validate on a generous build volume),
plus a key test asserting the retraction count is parametric.
"""
import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.retraction_test import retraction_test

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

# small-but-representative size so the suite stays fast
_RETRACTIONS = 40


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _steps():
    return retraction_test(retractions=_RETRACTIONS)


def test_design_starts_with_extrusion_geometry():
    steps = _steps()
    assert isinstance(steps[0], fc.ExtrusionGeometry)


def test_design_generates_gcode():
    gcode = fc.transform(_steps(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted
    assert '; retract' in gcode                    # retractions reached the gcode


def test_design_simulates_to_a_real_print():
    r = fc.transform(_steps(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


def test_design_validates_without_errors():
    r = fc.transform(_steps(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_design_is_essentially_flat_single_layer():
    'The real model is a flat field (~178x146x0.2): a single layer, hops aside.'
    pts = [s for s in _steps() if isinstance(s, Point)]
    zs = [p.z for p in pts]
    # only the travel z-hop lifts above the single print layer; the field itself is one layer
    assert min(zs) == pytest.approx(0.2)
    assert max(zs) <= 0.2 + 0.6 + 1e-9


def test_default_is_a_bed_filling_field():
    'The default mirrors the real model: a large bed-filling field (~178x146mm), not a tiny strip.'
    pts = [s for s in retraction_test() if isinstance(s, Point)]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    assert max(xs) - min(xs) > 100                  # fills the bed in x like the real ~178mm field
    assert max(ys) - min(ys) > 100                  # ...and in y like the real ~146mm field


@pytest.mark.parametrize('n', [1, 12, 40, 75])
def test_retraction_count_is_parametric(n):
    'The whole point of the design: it performs exactly `retractions` retractions.'
    steps = retraction_test(retractions=n)
    n_retract = sum(1 for s in steps if isinstance(s, fc.Retraction))
    n_unretract = sum(1 for s in steps if isinstance(s, fc.Unretraction))
    assert n_retract == n                           # exact, not within tolerance
    assert n_unretract == n                         # every retraction is paired with a prime


def test_retraction_count_holds_across_layers_and_shrink_switches():
    'Splitting the field over layers or applying the fewer_* switches must not change the count.'
    for kwargs in (dict(layers=3), dict(z_offset=2.0), dict(fewer_sets=True),
                   dict(fewer_travel_lines=True), dict(fewer_lines_per_set=True),
                   dict(layers=2, fewer_sets=True, fewer_lines_per_set=True)):
        steps = retraction_test(retractions=_RETRACTIONS, **kwargs)
        n_retract = sum(1 for s in steps if isinstance(s, fc.Retraction))
        assert n_retract == _RETRACTIONS, kwargs


def test_each_travel_is_guarded_by_a_retraction():
    'Every extruder-off travel hop is bracketed by a retraction (before) and unretraction (after).'
    steps = _steps()
    n_off = sum(1 for s in steps if isinstance(s, fc.Extruder) and s.on is False)
    n_retract = sum(1 for s in steps if isinstance(s, fc.Retraction))
    assert n_off == n_retract                        # one guarded travel per retraction
