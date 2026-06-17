"""The plot backend as a fold over the Toolpath IR.

The design is resolved (user steps only, extruder defaulting on) to `Segment`s, which this
fold turns into the plot `PlotData` paths - reusing the existing colour (`update_color`), path
and annotation machinery. Line moves add one vertex; arc moves add their tessellated points.
Paths break on an extruder on/off transition (mirroring the previous render_visualize logic,
including the single-point-path edge case).
"""
from fullcontrol.common import Point as BasePoint
from fullcontrol.visualize.annotations import PlotAnnotation
from fullcontrol.ir import Segment

_PRECISION_XYZ = 3


def _add_vertex(state, plot_data, plot_controls, x, y, z, color=None):
    if x is not None:
        state.point.x = round(x, _PRECISION_XYZ)
    if y is not None:
        state.point.y = round(y, _PRECISION_XYZ)
    if z is not None:
        state.point.z = round(z, _PRECISION_XYZ)
    if color is not None:
        state.point.color = color
    state.point.update_color(state, plot_data, plot_controls)
    plot_data.paths[-1].add_point(state)
    state.point_count_now += 1


def _break_path_if_toggled(state, plot_data, plot_controls, on):
    'Start a new path when the extruder toggles (mirrors the render_visualize Extruder handler).'
    if on == state.extruder.on:
        return
    state.extruder.on = on
    if len(plot_data.paths[-1].xvals) > 1:
        plot_data.add_path(state, plot_data, plot_controls)
        state.path_count_now += 1
    else:  # single-point path: relabel it rather than starting a new one
        plot_data.paths[-1].extruder.on = on
        state.point.update_color(state, plot_data, plot_controls)
        if len(plot_data.paths[-1].colors) > 0:
            plot_data.paths[-1].colors[-1] = state.point.color


def visualize_from_ir(toolpath, state, plot_data, plot_controls):
    'Build PlotData paths/annotations from the resolved Toolpath, then clean up.'
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            _break_path_if_toggled(state, plot_data, plot_controls, not ev.travel)
            if ev.width is not None:
                state.extrusion_geometry.width = round(ev.width, _PRECISION_XYZ)
            if ev.height is not None:
                state.extrusion_geometry.height = round(ev.height, _PRECISION_XYZ)
            if ev.kind == 'arc':
                for px, py, pz in ev.arc_points:  # the tessellated curve
                    _add_vertex(state, plot_data, plot_controls, px, py, pz)
            else:
                _add_vertex(state, plot_data, plot_controls, ev.end[0], ev.end[1], ev.end[2], ev.color)
        elif isinstance(ev, PlotAnnotation):
            if ev.point is None:
                ev.point = BasePoint(x=state.point.x, y=state.point.y, z=state.point.z)
            plot_data.add_annotation(ev)
        # other events (extruder/printer/geometry/temps/... and MaterialEvent) have no plot effect
    plot_data.cleanup()
