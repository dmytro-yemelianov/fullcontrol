"""Correctness / robustness batch 1: edge-case guards and a pydantic-v2 modernisation."""

import fullcontrol as fc
from fullcontrol.geometry.reflect import reflectXY_mc
from fullcontrol.gcode.auxilliary_components import Hotend, Buildplate
from fullcontrol.visualize.bounding_box import BoundingBox


# reflectXY_mc divided by zero for a horizontal mirror line (slope 0) - it is public API
def test_reflectXY_mc_horizontal_line_does_not_crash():
    r = reflectXY_mc(fc.Point(x=3, y=5, z=7), 0, 2)   # reflect about y=2 -> (3, -1)
    assert abs(r.x - 3) < 1e-9
    assert abs(r.y - (-1)) < 1e-9
    assert r.z == 7


# Hotend/Buildplate emitted "SNone" when temp was unset
def test_hotend_none_temp_emits_nothing():
    assert Hotend(temp=None, wait=True).gcode(None) is None
    assert Hotend(temp=None, wait=False).gcode(None) is None


def test_buildplate_none_temp_emits_nothing():
    assert Buildplate(temp=None, wait=True).gcode(None) is None
    assert Buildplate(temp=None, wait=False).gcode(None) is None


def test_hotend_with_temp_still_emits():
    assert 'M109 S210' in Hotend(temp=210, wait=True).gcode(None)
    assert 'M104 S210' in Hotend(temp=210, wait=False).gcode(None)


# bounding box over an empty / point-less design produced a negative range from the sentinels
def test_bounding_box_empty_input_has_zero_range():
    bb = BoundingBox()
    bb.calc_bounds([])
    for attr in ('rangex', 'rangey', 'rangez', 'midx', 'midy', 'midz'):
        assert getattr(bb, attr) == 0, attr


def test_bounding_box_normal_input():
    bb = BoundingBox()
    bb.calc_bounds([fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=4, z=2)])
    assert bb.rangex == 10 and bb.midx == 5
    assert bb.rangey == 4 and bb.rangez == 2


# import/export round-trip must work on pydantic v2 (was using deprecated parse_obj)
def test_import_export_design_roundtrip(tmp_path):
    steps = [fc.Point(x=1, y=2, z=3), fc.Extruder(on=True), fc.Point(x=4, y=5, z=6)]
    path = str(tmp_path / 'design')
    fc.export_design(steps, path)
    loaded = fc.import_design(fc, path)
    assert len(loaded) == 3
    assert loaded[0].x == 1 and loaded[2].z == 6
    assert loaded[1].on is True
