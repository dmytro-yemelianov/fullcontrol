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


def test_every_gcode_step_class_has_a_renderer():
    # *Controls are config; Point/Arc are motion, emitted by the gcode dialect from the IR
    # (not render_gcode); every other gcode step class must have a render_gcode handler
    from fullcontrol.gcode.renderers import render_gcode
    default = render_gcode.dispatch(object)
    motion = {'Point', 'Arc'}
    names = {n for n in _public_step_classes(gc) if not n.endswith('Controls')} - motion
    assert len(names) >= 8  # guard against the discovery silently collecting nothing
    for name in sorted(names):
        cls = getattr(gc, name)
        assert render_gcode.dispatch(cls) is not default, f'{name} has no gcode renderer'


def test_motion_classes_are_emitted_by_the_gcode_dialect():
    # Point/Arc are rendered from the resolved IR by the dialect; a motion design produces G-lines
    import fullcontrol as fc
    g = fc.transform([fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=0, z=0.2),
                      fc.Arc(centre=fc.Point(x=15, y=0), end=fc.Point(x=10, y=0), direction='clockwise')],
                     'gcode', fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert any(ln.startswith('G1 ') for ln in g.splitlines())
    assert any(ln.startswith('G2 ') or ln.startswith('G3 ') for ln in g.splitlines())


def test_visualize_step_classes_are_handled_by_the_plot_backend():
    # the plot backend now folds the resolved IR (no render_visualize); a design exercising the
    # visualize step classes (Point, Arc, Extruder, ExtrusionGeometry, PlotAnnotation) must
    # produce paths and the annotation
    import fullcontrol as fc
    pd = fc.transform(
        [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.ExtrusionGeometry(width=0.5, height=0.2),
         fc.Point(x=10, y=0, z=0.2),
         fc.Arc(centre=fc.Point(x=10, y=5), end=fc.Point(x=10, y=10), direction='clockwise'),
         fc.Extruder(on=False), fc.Point(x=0, y=10, z=0.2),
         fc.PlotAnnotation(label='here')],
        'plot', fc.PlotControls(raw_data=True, printer_name='generic'), show_tips=False)
    assert len(pd.paths) >= 2                      # extrude path(s) + the travel path
    assert any(len(p.xvals) > 5 for p in pd.paths)  # the arc tessellated into many vertices
    assert any(a['label'] == 'here' for a in pd.annotations)
