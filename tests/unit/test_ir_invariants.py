"""check_invariants makes the v2 IR `invariants` declaration load-bearing (enforceable)."""
import pytest

import fullcontrol as fc
from fullcontrol.ir import resolve, check_invariants
from fullcontrol.ir.toolpath import Toolpath, Segment


def _controls(**init):
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'nozzle_temp': 210, **init})


def _vase():
    return [fc.ExtrusionGeometry(width=0.6, height=0.2),
            fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2),
            fc.Point(x=0, y=10, z=0.4), fc.Point(x=0, y=0, z=0.6)]


def test_clean_vase_satisfies_geometry_invariants():
    tp = resolve(_vase(), _controls())
    rep = check_invariants(tp, ['non_negative_extrusion', 'monotonic_layer_z'])
    assert rep.ok
    assert {r.name for r in rep.results} == {'non_negative_extrusion', 'monotonic_layer_z'}
    assert all(r.checked and r.ok and not r.violations for r in rep.results)


def test_monotonic_layer_z_flags_a_step_down():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=0, y=0, z=0.2), fc.Point(x=10, y=0, z=2.0),
             fc.Point(x=10, y=10, z=0.5)]            # z drops 2.0 -> 0.5
    rep = check_invariants(resolve(steps, _controls()), ['monotonic_layer_z'])
    r = rep.results[0]
    assert not rep.ok and not r.ok and r.violations          # the downward step is reported


def test_within_build_volume_needs_the_volume_and_flags_out_of_bounds():
    tp = resolve([fc.ExtrusionGeometry(width=0.6, height=0.2),
                  fc.Point(x=5, y=5, z=0.2), fc.Point(x=300, y=5, z=0.2)], _controls())
    # without a build_volume the invariant can't be checked -> vacuously ok but checked=False
    skipped = check_invariants(tp, ['within_build_volume']).results[0]
    assert skipped.ok and not skipped.checked
    # with a 200^3 volume the X=300 point is out of bounds
    rep = check_invariants(tp, ['within_build_volume'], build_volume=(200, 200, 200))
    assert not rep.ok and rep.results[0].checked and rep.results[0].violations
    # a generous volume passes
    assert check_invariants(tp, ['within_build_volume'], build_volume=(500, 500, 500)).ok


def test_bounded_flow_flags_excessive_volumetric_flow():
    tp = resolve(_vase(), _controls(print_speed=6000))
    assert check_invariants(tp, ['bounded_flow']).results[0].checked is False   # needs max_flow
    rep_ok = check_invariants(tp, ['bounded_flow'], max_flow=100.0)
    rep_bad = check_invariants(tp, ['bounded_flow'], max_flow=0.01)
    assert rep_ok.ok and not rep_bad.ok and rep_bad.results[0].violations


def test_no_cold_extrusion_uses_hotend_events():
    # default resolve includes the start procedure, which heats the hotend -> no cold extrusion
    assert check_invariants(resolve(_vase(), _controls()), ['no_cold_extrusion']).ok
    # extruder on but no Hotend event (procedures stripped) -> cold extrusion violation
    cold_steps = [fc.ExtrusionGeometry(width=0.6, height=0.2), fc.Extruder(on=True),
                  fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    cold = resolve(cold_steps, _controls(), include_procedures=False)
    bad = check_invariants(cold, ['no_cold_extrusion'])
    assert not bad.ok and bad.results[0].violations


def test_non_negative_extrusion_flags_a_negative_volume():
    seg = Segment(start=(0, 0, 0.2), end=(10, 0, 0.2), travel=False, speed=1000, length=10,
                  deposited_volume=-1.0, filament_length=-0.4, source_index=0)
    rep = check_invariants(Toolpath([seg]), ['non_negative_extrusion'])
    assert not rep.ok and rep.results[0].violations


def test_unknown_invariant_rejected_and_report_helpers():
    tp = resolve(_vase(), _controls())
    with pytest.raises(ValueError, match='unknown invariant'):
        check_invariants(tp, ['not_a_real_invariant'])
    bad_tp = resolve([fc.ExtrusionGeometry(width=0.6, height=0.2), fc.Point(x=0, y=0, z=0.2),
                      fc.Point(x=10, y=0, z=2.0), fc.Point(x=10, y=10, z=0.5)], _controls())
    with pytest.raises(ValueError, match='invariant'):
        check_invariants(bad_tp, ['monotonic_layer_z']).raise_if_violated()
