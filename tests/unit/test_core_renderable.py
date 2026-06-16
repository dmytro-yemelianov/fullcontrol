"""Core data classes (fullcontrol.core.*) are directly renderable by the gcode and visualize
backends, not only their combined backend subclasses. This lets backend-free code (e.g. the
geometry generators) build designs from core classes that still render identically.
"""
import fullcontrol as fc
from fullcontrol.core.point import Point as CorePoint
from fullcontrol.core.extrusion_classes import Extruder as CoreExtruder, ExtrusionGeometry as CoreGeom


def _ctrl():
    return fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})


def test_core_point_design_renders_identical_gcode_to_combined():
    core = [CorePoint(x=0, y=0, z=0.2), CoreExtruder(on=True),
            CoreGeom(width=0.5, height=0.2),
            CorePoint(x=10, y=0, z=0.2), CorePoint(x=10, y=10, z=0.2)]
    combined = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.ExtrusionGeometry(width=0.5, height=0.2),
                fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    assert fc.transform(core, 'gcode', _ctrl(), show_tips=False) == \
           fc.transform(combined, 'gcode', _ctrl(), show_tips=False)


def test_core_point_design_renders_identical_plot_to_combined():
    core = [CorePoint(x=0, y=0, z=0.2), CoreExtruder(on=True),
            CorePoint(x=10, y=0, z=0.2), CorePoint(x=10, y=10, z=0.2)]
    combined = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    pc = lambda: fc.PlotControls(raw_data=True, printer_name='generic')
    a = fc.transform(core, 'plot', pc(), show_tips=False)
    b = fc.transform(combined, 'plot', pc(), show_tips=False)
    assert a.paths[-1].xvals == b.paths[-1].xvals
    assert a.paths[-1].yvals == b.paths[-1].yvals


def test_core_point_count_total_includes_core_points():
    from fullcontrol.visualize.state import State
    from fullcontrol.visualize.controls import PlotControls
    steps = [CorePoint(x=0, y=0, z=0.2), CoreExtruder(on=True), CorePoint(x=10, y=0, z=0.2)]
    assert State(steps, PlotControls(printer_name='generic')).point_count_total == 2
