"""transform self-verifies when initialization_data declares `invariants` (opt-in)."""
import pytest

import fullcontrol as fc


def _controls(**init):
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'nozzle_temp': 210, **init})


def _vase():
    return [fc.ExtrusionGeometry(width=0.6, height=0.2),
            fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2),
            fc.Point(x=0, y=10, z=0.4), fc.Point(x=0, y=0, z=0.6)]


def _z_down():
    return [fc.ExtrusionGeometry(width=0.6, height=0.2), fc.Point(x=0, y=0, z=0.2),
            fc.Point(x=10, y=0, z=2.0), fc.Point(x=10, y=10, z=0.5)]   # z drops 2.0 -> 0.5


def test_no_invariants_declared_is_a_no_op():
    'Default transform is unchanged when no invariants are declared.'
    gc = fc.transform(_vase(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gc, str) and 'G1' in gc


def test_clean_design_passes_declared_invariants():
    gc = fc.transform(_vase(), 'gcode',
                      _controls(invariants=['non_negative_extrusion', 'monotonic_layer_z']),
                      show_tips=False)
    assert isinstance(gc, str)                       # no raise -> result returned normally


def test_violated_invariant_raises():
    with pytest.raises(ValueError, match='invariant'):
        fc.transform(_z_down(), 'gcode', _controls(invariants=['monotonic_layer_z']),
                     show_tips=False)


def test_within_build_volume_uses_the_build_volume():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=5, y=5, z=0.2), fc.Point(x=300, y=5, z=0.2)]   # X=300 out of a 200 bed
    with pytest.raises(ValueError, match='within_build_volume'):
        fc.transform(steps, 'gcode',
                     _controls(invariants=['within_build_volume'],
                               build_volume_x=200, build_volume_y=200, build_volume_z=200),
                     show_tips=False)


def test_warn_mode_does_not_raise(capsys):
    gc = fc.transform(_z_down(), 'gcode',
                      _controls(invariants=['monotonic_layer_z'], invariant_mode='warn'),
                      show_tips=False)
    assert isinstance(gc, str)                       # produced output despite the violation
    assert 'monotonic_layer_z' in capsys.readouterr().out


def test_invariants_checked_for_any_result_type():
    'The self-verify runs before the backend, so it guards plot/simulate/validate too.'
    with pytest.raises(ValueError, match='invariant'):
        fc.transform(_z_down(), 'simulation', _controls(invariants=['monotonic_layer_z']),
                     show_tips=False)
