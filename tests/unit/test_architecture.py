"""Architectural invariants for the gcode/visualize combination layer.

The user-facing classes (fc.Point, fc.Extruder, ...) are assembled in
combinations/gcode_and_visualize/classes.py by combining each backend class with
the other backend's pass-through mixin. That file is maintained by hand, so these
tests fail loudly if a backend step class is ever added without being exposed there
(the documented drift risk) - keeping the layer explicit and IDE-friendly without
resorting to metaprogramming.
"""
import inspect

import fullcontrol.gcode as gc
import fullcontrol.visualize as vis
import fullcontrol.combinations.gcode_and_visualize.classes as combined
from fullcontrol.base import BaseModelPlus


def _public_step_classes(module):
    'public BaseModelPlus subclasses actually defined within this backend package'
    return {
        name for name, obj in vars(module).items()
        if inspect.isclass(obj) and not name.startswith('_')
        and issubclass(obj, BaseModelPlus)
        and obj.__module__.startswith(module.__name__ + '.')
    }


def test_every_gcode_step_class_is_exposed_in_combinations():
    missing = sorted(n for n in _public_step_classes(gc) if not hasattr(combined, n))
    assert not missing, f'gcode classes missing from the combinations layer: {missing}'


def test_every_visualize_step_class_is_exposed_in_combinations():
    missing = sorted(n for n in _public_step_classes(vis) if not hasattr(combined, n))
    assert not missing, f'visualize classes missing from the combinations layer: {missing}'


def test_combined_step_classes_answer_both_gcode_and_visualize():
    # *Controls are configuration objects, not steps in the design list, so they are
    # not processed by the gcode/visualize loops and don't carry both render methods.
    names = {n for n in _public_step_classes(gc) | _public_step_classes(vis)
             if not n.endswith('Controls')}
    assert len(names) >= 10  # guard against the discovery silently collecting nothing
    for name in sorted(names):
        cls = getattr(combined, name)
        assert callable(getattr(cls, 'gcode', None)), f'{name}.gcode not callable'
        assert callable(getattr(cls, 'visualize', None)), f'{name}.visualize not callable'
