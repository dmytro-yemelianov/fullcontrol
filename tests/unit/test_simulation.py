"""The simulation backend (result_type='simulation'): time/material/flow estimates."""
from types import SimpleNamespace

import fullcontrol as fc
from fullcontrol.simulate.result import SimulationResult
from fullcontrol.simulate.renderers import render_simulate, _distance


def test_distance_ignores_axes_not_defined_in_both_points():
    assert abs(_distance(fc.Point(x=0, y=0, z=0), fc.Point(x=3, y=4, z=0)) - 5) < 1e-9
    assert abs(_distance(fc.Point(x=0, y=0, z=None), fc.Point(x=3, y=4, z=5)) - 5) < 1e-9


def _stub_state():
    return SimpleNamespace(
        point=fc.Point(x=0, y=0, z=0),
        extruder=SimpleNamespace(on=True, volume_to_e=1.0),
        printer=SimpleNamespace(print_speed=600, travel_speed=6000),  # 600 mm/min = 10 mm/s
        extrusion_geometry=SimpleNamespace(area=0.08),
    )


def test_point_handler_accumulates_time_volume_flow():
    state, r = _stub_state(), SimulationResult()
    render_simulate(fc.Point(x=10, y=0, z=0), state, r)  # 10mm @ 600mm/min = 1.0s
    assert abs(r.total_time_s - 1.0) < 1e-9
    assert abs(r.print_time_s - 1.0) < 1e-9
    assert abs(r.extruding_distance - 10) < 1e-9
    assert abs(r.extruded_volume - 0.8) < 1e-9      # 10 * 0.08
    assert abs(r.filament_length - 0.8) < 1e-9      # volume_to_e = 1
    assert abs(r.max_flow_rate - 0.8) < 1e-9        # 0.8 mm^3 / 1 s
    assert r.segment_count == 1


def test_travel_move_counts_as_travel_not_print():
    state, r = _stub_state(), SimulationResult()
    state.extruder.on = False
    render_simulate(fc.Point(x=60, y=0, z=0), state, r)  # 60mm @ 6000mm/min = 0.6s
    assert abs(r.travel_time_s - 0.6) < 1e-9
    assert r.print_time_s == 0.0
    assert abs(r.travel_distance - 60) < 1e-9
    assert r.extruded_volume == 0.0


def test_transform_simulation_returns_sensible_result():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    r = fc.transform(steps, 'simulation',
                     fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert isinstance(r, SimulationResult)
    assert r.total_time_s > 0
    assert r.extruding_distance >= 19          # the two 10 mm user edges
    assert r.extruded_volume > 0
    assert r.max_flow_rate > 0
    assert r.segment_count > 0
    assert 'time ~' in r.summary()


def test_simulation_is_a_registered_backend():
    from fullcontrol.combinations.gcode_and_visualize.backends import available_backends
    assert 'simulation' in available_backends()
