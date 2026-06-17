"""The simulation backend (result_type='simulation'): time/material/flow estimates.

Simulation is a stateless fold over the Toolpath IR; these test the fold and the IR _distance
helper directly, plus the end-to-end transform.
"""
import fullcontrol as fc
from fullcontrol.simulate.result import SimulationResult
from fullcontrol.simulate.run import simulate_from_ir
from fullcontrol.ir.toolpath import _distance, Toolpath, Segment


def test_distance_ignores_axes_not_defined_in_both_points():
    assert abs(_distance(fc.Point(x=0, y=0, z=0), fc.Point(x=3, y=4, z=0)) - 5) < 1e-9
    assert abs(_distance(fc.Point(x=0, y=0, z=None), fc.Point(x=3, y=4, z=5)) - 5) < 1e-9


def test_fold_accumulates_time_volume_flow_for_an_extruding_segment():
    # a 10 mm extruding segment at 600 mm/min (=10 mm/s): 1.0 s, 0.8 mm^3, flow 0.8 mm^3/s
    seg = Segment(start=(0, 0, 0), end=(10, 0, 0), travel=False, speed=600, length=10,
                  deposited_volume=0.8, filament_length=0.8, source_index=0)
    r = simulate_from_ir(Toolpath([seg]))
    assert abs(r.total_time_s - 1.0) < 1e-9
    assert abs(r.print_time_s - 1.0) < 1e-9
    assert abs(r.extruding_distance - 10) < 1e-9
    assert abs(r.extruded_volume - 0.8) < 1e-9
    assert abs(r.filament_length - 0.8) < 1e-9
    assert abs(r.max_flow_rate - 0.8) < 1e-9
    assert r.segment_count == 1


def test_fold_counts_travel_segment_as_travel_not_print():
    seg = Segment(start=(0, 0, 0), end=(60, 0, 0), travel=True, speed=6000, length=60,
                  deposited_volume=0.0, filament_length=0.0, source_index=0)
    r = simulate_from_ir(Toolpath([seg]))
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
