"""Consistency of the data-class definitions: every fullcontrol data class uses BaseModelPlus
(dict access, update_from, the friendly unknown-field error), and the visualize Path does not
share mutable default lists between instances.
"""
import pytest

from fullcontrol.core.base import BaseModelPlus
from fullcontrol.geometry.vector import Vector
from fullcontrol.geometry.polar import PolarPoint
from fullcontrol.visualize.path import Path


def test_geometry_data_classes_use_basemodelplus():
    assert issubclass(Vector, BaseModelPlus)
    assert issubclass(PolarPoint, BaseModelPlus)


def test_basemodelplus_features_on_geometry_classes():
    v = Vector(x=1, y=2, z=3)
    assert v['x'] == 1                       # dict-style access from BaseModelPlus
    with pytest.raises(Exception):
        Vector(x=1, q=9)                     # unknown field rejected with a helpful message
    assert PolarPoint(radius=1, angle=2)['radius'] == 1


def test_path_instances_do_not_share_default_lists():
    a, b = Path(), Path()
    a.xvals.append(1)
    assert b.xvals == [], 'Path instances must not share a mutable default list'
