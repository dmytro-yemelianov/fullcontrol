"""HIGH-5: XYZBC (5-axis B-C bed) inverse kinematics must apply bc_intercept correctly.

Ground-truth oracle values come from the original (pre-regression) behaviour:
the workpiece origin sits at the rotation centre (bc_intercept), so for an
intercept at x=10:
  - model x=0, B=C=0           -> system x=10
  - model x=1, B=C=0           -> system x=11
  - model x=1, B=45, C=0       -> system x=10.7071068, z=-0.7071068
i.e. system = R(B,C) @ model + bc_intercept.
"""
import math
from types import SimpleNamespace

import numpy as np

from fullcontrol.common import Point as CommonPoint
from lab.fullcontrol.multiaxis.gcode.XYZBC.point import Point


def _state(intercept=(10, 0, 0), seed=(0, 0, 0, 0, 0)):
    x, y, z, b, c = seed
    return SimpleNamespace(
        point=Point(x=x, y=y, z=z, b=b, c=c),
        printer=SimpleNamespace(bc_intercept=CommonPoint(x=intercept[0], y=intercept[1], z=intercept[2])),
    )


def test_intercept_applied_at_zero_rotation():
    s = Point(x=0, y=0, z=0, b=0, c=0).inverse_kinematics(_state())
    assert abs(s.x - 10) < 1e-6 and abs(s.y) < 1e-6 and abs(s.z) < 1e-6


def test_translation_with_intercept_no_rotation():
    s = Point(x=1, y=0, z=0, b=0, c=0).inverse_kinematics(_state())
    assert abs(s.x - 11) < 1e-6


def test_b_rotation_about_intercept():
    s = Point(x=1, y=0, z=0, b=45, c=0).inverse_kinematics(_state())
    assert abs(s.x - 10.7071068) < 1e-5
    assert abs(s.z - (-0.7071068)) < 1e-5


def test_matches_rotation_plus_intercept_general_case():
    model_xyz, bc, intercept = (2.0, -1.5, 0.7), (30, 50), (3, -2, 1)
    s = Point(x=model_xyz[0], y=model_xyz[1], z=model_xyz[2], b=bc[0], c=bc[1]).inverse_kinematics(_state(intercept=intercept))
    b, c = math.radians(bc[0]), math.radians(bc[1])
    R = np.array([
        [math.cos(b) * math.cos(c), -math.sin(c) * math.cos(b), math.sin(b)],
        [math.sin(c), math.cos(c), 0],
        [-math.sin(b) * math.cos(c), math.sin(b) * math.sin(c), math.cos(b)],
    ])
    expected = R @ np.array(model_xyz) + np.array(intercept)
    assert abs(s.x - expected[0]) < 1e-6
    assert abs(s.y - expected[1]) < 1e-6
    assert abs(s.z - expected[2]) < 1e-6
