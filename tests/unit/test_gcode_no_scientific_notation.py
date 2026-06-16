"""HIGH-3: gcode numeric fields must never be emitted in scientific notation.

`:.6` (6 significant figures) yields strings like `1e-05` or `1.23457e+06`, which most
firmware rejects. The fix uses fixed-decimal formatting (`:.6f`, trailing zeros stripped)
consistently, matching the already-correct Extruder.e_gcode.
"""
from types import SimpleNamespace

from fullcontrol.gcode.extrusion_classes import StationaryExtrusion
from fullcontrol.gcode.renderers import render_gcode
from lab.fullcontrol.multiaxis.gcode.XYZB.point import Point as XYZBPoint
from lab.fullcontrol.multiaxis.gcode.XYZBC.point import Point as XYZBCPoint
from lab.fullcontrol.multiaxis.gcode.XYZC0B1.point import Point as XYZC0B1Point


def _numeric_part_has_no_exponent(field_value: str):
    # field_value looks like "X1234567" or "E0.00001"; the leading char is the axis letter
    assert 'e' not in field_value[1:].lower(), f'scientific notation in {field_value!r}'


def test_stationary_extrusion_small_value_not_scientific():
    state = SimpleNamespace(
        printer=SimpleNamespace(speed_changed=False),
        extruder=SimpleNamespace(get_and_update_volume=lambda v: v, volume_to_e=1),
    )
    line = render_gcode(StationaryExtrusion(volume=0.00001, speed=1000), state)
    e_field = line.split()[-1]  # e.g. 'E0.00001'
    assert e_field.startswith('E')
    _numeric_part_has_no_exponent(e_field)


def _assert_axis_fields_plain(gcode_str):
    for field in gcode_str.split():
        _numeric_part_has_no_exponent(field)


def test_xyzb_large_coordinate_not_scientific():
    prev = XYZBPoint(x=0, y=0, z=0, b=0)
    cur = XYZBPoint(x=1234567.0, y=0, z=0, b=0)
    s = cur.XYZB_gcode(cur, prev)
    _assert_axis_fields_plain(s)


def test_xyzbc_large_coordinate_not_scientific():
    prev = XYZBCPoint(x=0, y=0, z=0, b=0, c=0)
    cur = XYZBCPoint(x=1234567.0, y=0, z=0, b=0, c=0)
    s = cur.XYZBC_gcode(cur, prev)
    _assert_axis_fields_plain(s)


def test_xyzc0b1_large_coordinate_not_scientific():
    prev = XYZC0B1Point(x=0, y=0, z=0, b=0, c=0)
    cur = XYZC0B1Point(x=1234567.0, y=0, z=0, b=0, c=0)
    s = cur.XYZBC_gcode(cur, prev)
    _assert_axis_fields_plain(s)
