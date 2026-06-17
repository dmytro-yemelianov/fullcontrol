"""Exact-message characterisation of validate's geometric checks (bounds, negative-z,
first-layer, extrusion-geometry). These pin the precise wording AND the reported coordinates so
the columnar (numpy) re-implementation of these folds stays byte-identical to the object version.
"""
import fullcontrol as fc

_BV = {'build_volume_x': 100, 'build_volume_y': 100, 'build_volume_z': 100, 'nozzle_temp': 210}


def _validate(steps, init=_BV):
    return fc.transform(steps, 'validate',
                        fc.GcodeControls(printer_name='generic', initialization_data=init), show_tips=False)


def _emsgs(r):
    return [e['message'] for e in r.errors]


def _wmsgs(r):
    return [w['message'] for w in r.warnings]


def test_bounds_error_reports_count_and_first_offending_point():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=50, z=0.2)])
    assert '1 point(s) outside the build volume (100x100x100); first at (x=250.0, y=50.0, z=0.2)' in _emsgs(r)


def test_bounds_error_counts_all_and_reports_the_first():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True),
                   fc.Point(x=250, y=10, z=0.2), fc.Point(x=10, y=300, z=0.2)])
    assert '2 point(s) outside the build volume (100x100x100); first at (x=250.0, y=10.0, z=0.2)' in _emsgs(r)


def test_negative_z_count_message():
    r = _validate([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=-1)])
    assert '1 point(s) have negative z (below the bed)' in _wmsgs(r)


def test_first_layer_z_at_or_below_zero():
    r = _validate([fc.Point(x=10, y=10, z=0), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0)])
    assert 'first extrusion move is at z=0.0 (<= 0) - nozzle may be at or below the bed' in _wmsgs(r)


def test_zero_extrusion_geometry_reports_width_height():
    r = _validate([fc.ExtrusionGeometry(width=0, height=0.2), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)])
    assert ('extruding with a zero/undefined extrusion geometry (width=0.0, height=0.2) '
            '- no material will be extruded') in _wmsgs(r)


def test_in_bounds_design_has_no_geometric_warnings():
    r = _validate([fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Point(x=10, y=10, z=0.2),
                   fc.Extruder(on=True), fc.Point(x=50, y=50, z=0.2)])
    assert not any('build volume' in m for m in _emsgs(r))
    assert not any('negative z' in m or 'first extrusion' in m or 'extrusion geometry' in m for m in _wmsgs(r))
