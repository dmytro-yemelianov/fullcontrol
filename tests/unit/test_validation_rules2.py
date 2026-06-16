"""Further pre-flight validation rules: extruding with no/zero extrusion geometry (silent
no-extrusion), and a low-noise stringing heuristic (long travels without retraction, only
flagged when the design uses retraction elsewhere).
"""
import fullcontrol as fc

_BASE = {'nozzle_temp': 210}


def _validate(steps, init=None):
    init = {**_BASE, **(init or {})}
    return fc.transform(steps, 'validate',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _msgs(r):
    return [i['message'] for i in r.issues]


# --- extruding with no/zero extrusion geometry ---

def test_zero_width_geometry_warns():
    r = _validate([fc.ExtrusionGeometry(width=0, height=0.2),
                   fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('extru' in m and ('geometry' in m or 'material' in m) for m in _msgs(r))


def test_zero_height_geometry_warns():
    r = _validate([fc.ExtrusionGeometry(height=0),
                   fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert any('extru' in m and ('geometry' in m or 'material' in m) for m in _msgs(r))


def test_normal_geometry_does_not_warn():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert not any('no material' in m for m in _msgs(r))


# --- stringing heuristic (long travel without retraction) ---

def test_long_travel_without_retraction_when_design_retracts_elsewhere_is_flagged():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Retraction(distance=1), fc.Unretraction(),         # design clearly uses retraction
             fc.Point(x=10, y=2, z=0.2),
             fc.Extruder(on=False), fc.Point(x=80, y=80, z=0.2),   # long travel, no retraction
             fc.Extruder(on=True), fc.Point(x=80, y=81, z=0.2)]
    r = _validate(steps)
    assert any('stringing' in m for m in _msgs(r))


def test_retracting_before_each_long_travel_is_not_flagged():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Retraction(distance=1), fc.Extruder(on=False), fc.Point(x=80, y=80, z=0.2),
             fc.Extruder(on=True), fc.Unretraction(), fc.Point(x=80, y=81, z=0.2)]
    r = _validate(steps)
    assert not any('stringing' in m for m in _msgs(r))


def test_design_that_never_retracts_is_not_nagged():
    # no Retraction anywhere -> we do not nag about stringing even with long travels
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=80, y=80, z=0.2),
             fc.Extruder(on=True), fc.Point(x=80, y=81, z=0.2)]
    r = _validate(steps)
    assert not any('stringing' in m for m in _msgs(r))
