"""Pre-flight validation backend (result_type='validate')."""
import pytest

import fullcontrol as fc
from fullcontrol.validate.result import ValidationResult

_BV = {'build_volume_x': 100, 'build_volume_y': 100, 'build_volume_z': 100, 'nozzle_temp': 210}


def _validate(steps, init):
    return fc.transform(steps, 'validate', fc.GcodeControls(printer_name='generic', initialization_data=init), show_tips=False)


def test_in_bounds_design_passes():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=50, z=0.2)], _BV)
    assert isinstance(r, ValidationResult)
    assert r.ok and not r.errors


def test_out_of_bounds_is_an_error():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=50, z=0.2)], _BV)
    assert not r.ok
    assert any('build volume' in e['message'] for e in r.errors)


def test_negative_z_warns():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=-1)], _BV)
    assert any('negative z' in w['message'] for w in r.warnings)


def test_no_build_volume_skips_bounds_check():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=999, y=999, z=0.2)], {'nozzle_temp': 210})
    assert not any('build volume' in e['message'] for e in r.errors)
    assert any('build volume not defined' in i['message'] for i in r.issues)


def test_cold_extrusion_warns_when_no_heating():
    # generic printer, no nozzle_temp override -> no heating command emitted -> cold extrusion risk
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)], {})
    assert any('cold extrusion' in w['message'] for w in r.warnings)


def test_heated_design_has_no_cold_warning():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)], _BV)
    assert not any('cold extrusion' in w['message'] for w in r.warnings)


def test_raise_if_errors_raises_on_out_of_bounds():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=50, z=0.2)], _BV)
    with pytest.raises(ValueError, match='validation failed'):
        r.raise_if_errors()


def test_validate_is_a_registered_backend():
    from fullcontrol.combinations.gcode_and_visualize.backends import available_backends
    assert 'validate' in available_backends()
