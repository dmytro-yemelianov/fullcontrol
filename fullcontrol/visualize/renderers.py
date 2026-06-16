"""Visualisation as a renderer (functools.singledispatch) rather than a .visualize()
method on every step class.

The visualize driver dispatches each step through render_visualize(...). A step with
no visualisation effect (e.g. a Printer/Fan/temperature change) falls through to the
default handler and does nothing.
"""
from functools import singledispatch
from math import pi

from fullcontrol.visualize.point import Point
from fullcontrol.visualize.arc import Arc
from fullcontrol.visualize.extrusion_classes import Extruder, ExtrusionGeometry
from fullcontrol.visualize.annotations import PlotAnnotation
from fullcontrol.common import Point as BasePoint
from fullcontrol.core.arc import arc_geometry, arc_points

_PRECISION_XYZ = 3  # decimal places for x/y/z stored in plot_data


@singledispatch
def render_visualize(step, state, plot_data, plot_controls):
    'default: a step with no visualisation representation does nothing'
    return None


@render_visualize.register
def _(step: Point, state, plot_data, plot_controls):
    change_check = False
    if step.x is not None and step.x != state.point.x:
        state.point.x = round(step.x, _PRECISION_XYZ)
        change_check = True
    if step.y is not None and step.y != state.point.y:
        state.point.y = round(step.y, _PRECISION_XYZ)
        change_check = True
    if step.z is not None and step.z != state.point.z:
        state.point.z = round(step.z, _PRECISION_XYZ)
        change_check = True
    if step.color is not None and step.color != state.point.color:
        state.point.color = step.color
        change_check = True
    if change_check:
        state.point.update_color(state, plot_data, plot_controls)
        plot_data.paths[-1].add_point(state)
        state.point_count_now += 1


@render_visualize.register
def _(step: Arc, state, plot_data, plot_controls):
    # tessellate the arc into points from the current position and render each as a Point,
    # reusing the Point handler's colour / path / bounds logic
    start = state.point
    geom = arc_geometry(step, start.x, start.y, start.z)
    for px, py, pz in arc_points(step, start.x, start.y, start.z, geom):
        render_visualize(Point(x=px, y=py, z=pz), state, plot_data, plot_controls)


@render_visualize.register
def _(step: Extruder, state, plot_data, plot_controls):
    if step.on is not None and step.on != state.extruder.on:
        state.extruder.on = step.on
        # if the current path has more than one point, start a new path; otherwise update the current one
        if len(plot_data.paths[-1].xvals) > 1:
            plot_data.add_path(state, plot_data, plot_controls)
            state.path_count_now += 1
        else:
            plot_data.paths[-1].extruder.on = step.on
            state.point.update_color(state, plot_data, plot_controls)
            if len(plot_data.paths[-1].colors) > 0:
                plot_data.paths[-1].colors[-1] = state.point.color


@render_visualize.register
def _(step: ExtrusionGeometry, state, plot_data, plot_controls):
    if step.width is not None and step.width != state.extrusion_geometry.width:
        state.extrusion_geometry.width = round(step.width, _PRECISION_XYZ)
    if step.height is not None and step.height != state.extrusion_geometry.height:
        state.extrusion_geometry.height = round(step.height, _PRECISION_XYZ)
    if step.diameter is not None:
        state.extrusion_geometry.width = round(step.diameter, _PRECISION_XYZ)
        state.extrusion_geometry.height = round(step.diameter, _PRECISION_XYZ)
    if step.area is not None:
        dia = 2*(step.area/pi)**0.5
        state.extrusion_geometry.width = round(dia, _PRECISION_XYZ)
        state.extrusion_geometry.height = round(dia, _PRECISION_XYZ)


@render_visualize.register
def _(step: PlotAnnotation, state, plot_data, plot_controls):
    if step.point is None:
        step.point = BasePoint(x=state.point.x, y=state.point.y, z=state.point.z)
    plot_data.add_annotation(step)
