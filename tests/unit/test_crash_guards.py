"""HIGH-6: unguarded crash paths on plausible inputs.

Covers:
  - points_only(): IndexError when every point is under-defined
  - linspace(): ZeroDivisionError for number_of_points == 1
  - midpoint(): UnboundLocalError when a coordinate is None
  - interpolated_point(): TypeError from arithmetic on a single None coordinate
  - TubeMesh: silent NaN mesh vertices when successive path points coincide
"""
import numpy as np

import fullcontrol as fc
from fullcontrol.extra_functions import linspace
from fullcontrol.visualize.tube_mesh import TubeMesh


def test_points_only_returns_empty_when_all_points_underdefined():
    steps = [fc.Point(x=0, y=0, z=None), fc.Point(x=1, y=1, z=None)]
    # no fully-defined point exists -> should return [] rather than IndexError
    assert fc.points_only(steps) == []


def test_linspace_single_point_returns_start():
    assert linspace(5.0, 10.0, 1) == [5.0]


def test_linspace_normal_case_unchanged():
    assert linspace(0.0, 10.0, 3) == [0.0, 5.0, 10.0]


def test_midpoint_handles_none_coordinate():
    m = fc.midpoint(fc.Point(x=0, y=0, z=None), fc.Point(x=2, y=4, z=None))
    assert m.x == 1 and m.y == 2 and m.z is None


def test_interpolated_point_handles_partial_none_coordinate():
    p = fc.interpolated_point(fc.Point(x=0, y=0, z=0), fc.Point(x=2, y=2, z=None), 0.5)
    assert p.x == 1 and p.y == 1 and p.z is None


def test_tube_mesh_no_nan_for_coincident_successive_points():
    path = [[0, 0, 0], [1, 0, 0], [1, 0, 0], [2, 0, 0]]  # duplicate at index 1->2
    tm = TubeMesh(path, 0.4, 0.4, sides=4, rounding_strength=1,
                  flat_sides=True, capped=False, inplace_path=False)
    assert not np.isnan(np.asarray(tm.mesh_points)).any()
