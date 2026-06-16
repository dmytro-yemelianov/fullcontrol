"""Per-step simulation as a singledispatch renderer (the simulation backend).

Mirrors the gcode/visualize renderers: each step updates the tracked State and
accumulates metrics into the SimulationResult. Steps with no effect on time/material
(Fan, Hotend, ...) fall through to the default.
"""
from functools import singledispatch

from fullcontrol.core.point import Point
from fullcontrol.core.printer import Printer
from fullcontrol.core.extrusion_classes import Extruder, ExtrusionGeometry, StationaryExtrusion


def _distance(p1, p2):
    'Euclidean distance, ignoring any axis not defined in both points.'
    dx = 0.0 if p1.x is None or p2.x is None else p2.x - p1.x
    dy = 0.0 if p1.y is None or p2.y is None else p2.y - p1.y
    dz = 0.0 if p1.z is None or p2.z is None else p2.z - p1.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


@singledispatch
def render_simulate(step, state, result):
    'default: a step that does not affect time/material'
    return None


@render_simulate.register
def _(step: Point, state, result):
    length = _distance(state.point, step)
    if length > 0:
        speed = state.printer.print_speed if state.extruder.on else state.printer.travel_speed
        if speed:
            t = length / speed * 60.0  # mm / (mm/min) -> minutes -> seconds
            result.total_time_s += t
            if state.extruder.on:
                result.print_time_s += t
                result.extruding_distance += length
                area = state.extrusion_geometry.area or 0.0
                vol = length * area
                result.extruded_volume += vol
                result.filament_length += vol * (state.extruder.volume_to_e or 0.0)
                if t > 0:
                    result.max_flow_rate = max(result.max_flow_rate, vol / t)
            else:
                result.travel_time_s += t
                result.travel_distance += length
            result.segment_count += 1
    state.point.update_from(step)


@render_simulate.register
def _(step: Printer, state, result):
    state.printer.update_from(step)


@render_simulate.register
def _(step: Extruder, state, result):
    state.extruder.update_from(step)
    # units/dia_feed are gcode-Extruder fields; a core Extruder (e.g. from geometry) lacks them
    if getattr(step, 'units', None) is not None or getattr(step, 'dia_feed', None) is not None:
        state.extruder.update_e_ratio()


@render_simulate.register
def _(step: ExtrusionGeometry, state, result):
    state.extrusion_geometry.update_from(step)
    if step.width is not None or step.height is not None or step.diameter is not None or step.area_model is not None:
        try:
            state.extrusion_geometry.update_area()
        except TypeError:
            pass


@render_simulate.register
def _(step: StationaryExtrusion, state, result):
    result.extruded_volume += step.volume
    result.filament_length += step.volume * (state.extruder.volume_to_e or 0.0)
