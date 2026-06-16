"""transform() dispatches through an open backend registry."""
import pytest

import fullcontrol as fc
from fullcontrol.combinations.gcode_and_visualize.backends import (
    register_backend, available_backends, _BACKENDS,
)


def test_builtin_backends_registered():
    assert 'gcode' in available_backends()
    assert 'plot' in available_backends()


def test_unknown_backend_raises_clear_error():
    with pytest.raises(ValueError, match='not recognized'):
        fc.transform([fc.Point(x=0, y=0, z=0)], 'no_such_backend', show_tips=False)


def test_new_backend_can_be_registered_and_used():
    captured = {}
    register_backend('_test_backend', fc.GcodeControls,
                     lambda steps, controls, show_tips: captured.setdefault('n', len(steps)))
    try:
        fc.transform([fc.Point(x=0, y=0, z=0), fc.Point(x=1, y=0, z=0)], '_test_backend', show_tips=False)
        assert captured['n'] >= 2  # runner received the fixed step list
    finally:
        _BACKENDS.pop('_test_backend', None)
