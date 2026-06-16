"""Extra pre-flight validation rules: temperature sanity, speed sanity, first-layer Z, and
retraction balance. These extend the build-volume / cold-extrusion checks in test_validation.py.
"""
import fullcontrol as fc

_BV = {'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200, 'nozzle_temp': 210}


def _validate(steps, init=None):
    init = {**_BV, **(init or {})}
    return fc.transform(steps, 'validate',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _msgs(result):
    return [i['message'] for i in result.issues]


# --- temperature sanity ---

def test_excessive_nozzle_temp_warns():
    r = _validate([fc.Hotend(temp=400, wait=True), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('nozzle' in m and 'high' in m for m in _msgs(r))


def test_low_nozzle_temp_warns():
    r = _validate([fc.Hotend(temp=120, wait=True), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('nozzle' in m and 'low' in m for m in _msgs(r))


def test_excessive_bed_temp_warns():
    r = _validate([fc.Buildplate(temp=200, wait=True), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('bed' in m and 'high' in m for m in _msgs(r))


def test_normal_temps_do_not_warn():
    r = _validate([fc.Hotend(temp=210, wait=True), fc.Buildplate(temp=60, wait=True),
                   fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert not any('temp' in m for m in _msgs(r))


# --- speed sanity ---

def test_zero_print_speed_is_an_error():
    r = _validate([fc.Printer(print_speed=0), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert not r.ok
    assert any('speed' in e['message'] for e in r.errors)


def test_excessive_speed_warns():
    r = _validate([fc.Printer(print_speed=120000), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('speed' in w['message'] for w in r.warnings)


def test_normal_speed_does_not_warn():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert not any('speed' in m for m in _msgs(r))


# --- first-layer Z ---

def test_first_extrusion_at_zero_z_warns():
    r = _validate([fc.Point(x=10, y=10, z=0), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0)])
    assert any('first' in m and 'z' in m.lower() for m in _msgs(r))


def test_normal_first_layer_does_not_warn():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert not any('first extrusion' in m for m in _msgs(r))


# --- retraction balance ---

def test_unbalanced_retraction_warns():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2),
                   fc.Retraction(distance=3)])  # never primed back
    assert any('retract' in m for m in _msgs(r))


def test_balanced_retraction_does_not_warn():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2),
                   fc.Retraction(distance=3), fc.Point(x=20, y=20, z=0.2), fc.Unretraction()])
    assert not any('left retracted' in m for m in _msgs(r))
