"""The columnar (numpy) fast-path for the Toolpath IR.

`ColumnarToolpath.from_toolpath` flattens an object Toolpath's Segments into parallel numpy
arrays; `simulate_columnar` is a vectorised re-implementation of the simulate fold over those
arrays. These tests pin the columnar fold to the object fold (the readable default) so the two
can never silently diverge, and exercise the array extraction directly.

Float summation is reordered by numpy's pairwise sum, so equivalence is asserted to a tight
relative tolerance rather than bit-identity (max_flow_rate, a reduction by max, *is* exact).
"""
import numpy as np

import fullcontrol as fc
from fullcontrol.simulate.run import simulate_from_ir, simulate_columnar
from fullcontrol.ir.toolpath import Toolpath, Segment, MaterialEvent
from fullcontrol.ir.columnar import ColumnarToolpath, resolve_columnar


def _assert_results_close(a, b):
    for field in ('total_time_s', 'print_time_s', 'travel_time_s', 'extruding_distance',
                  'travel_distance', 'extruded_volume', 'filament_length'):
        av, bv = getattr(a, field), getattr(b, field)
        assert av == 0 and bv == 0 or abs(av - bv) <= 1e-9 * max(abs(av), abs(bv)), \
            f'{field}: {av} vs {bv}'
    assert a.segment_count == b.segment_count
    assert a.max_flow_rate == b.max_flow_rate  # max reduction is order-independent -> exact


def test_columnar_extracts_segment_columns_and_aggregates_material():
    events = [
        Segment(start=(0, 0, 0), end=(10, 0, 0), travel=False, speed=600, length=10,
                deposited_volume=0.8, filament_length=0.8, source_index=0),
        Segment(start=(10, 0, 0), end=(10, 10, 0), travel=True, speed=6000, length=10,
                deposited_volume=0.0, filament_length=0.0, source_index=1),
        MaterialEvent(deposited_volume=2.0, filament_length=2.5, source_index=2),
    ]
    c = ColumnarToolpath.from_toolpath(Toolpath(events))
    assert c.n_segments == 2
    assert c.travel.tolist() == [False, True]
    assert c.speed.tolist() == [600.0, 6000.0]
    assert c.length.tolist() == [10.0, 10.0]
    assert c.deposited_volume.tolist() == [0.8, 0.0]
    np.testing.assert_array_equal(c.start[0], [0.0, 0.0, 0.0])
    np.testing.assert_array_equal(c.end[1], [10.0, 10.0, 0.0])
    assert c.material_volume == 2.0
    assert c.material_filament == 2.5


def test_undefined_axis_becomes_nan_in_columns():
    seg = Segment(start=(None, None, None), end=(1, 2, None), travel=True, speed=6000,
                  length=0, deposited_volume=0.0, filament_length=0.0, source_index=0)
    c = ColumnarToolpath.from_toolpath(Toolpath([seg]))
    assert np.isnan(c.start[0]).all()
    assert c.end[0, 0] == 1 and c.end[0, 1] == 2 and np.isnan(c.end[0, 2])


def test_columnar_fold_matches_object_fold_on_a_real_design():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True)]
    for i in range(1, 200):
        steps.append(fc.Point(x=i % 50, y=(i * 7) % 40, z=0.2 + i * 0.01))
        if i % 25 == 0:
            steps.append(fc.Extruder(on=(i % 50 != 0)))
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    from fullcontrol.ir import resolve
    toolpath = resolve(steps, controls)
    obj = simulate_from_ir(toolpath)
    col = simulate_columnar(ColumnarToolpath.from_toolpath(toolpath))
    _assert_results_close(obj, col)
    assert col.segment_count > 100  # sanity: this is a non-trivial design


def test_columnar_fold_matches_object_fold_with_arcs():
    steps = [fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
             fc.Point(x=0, y=30, z=0.2)]
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    from fullcontrol.ir import resolve
    toolpath = resolve(steps, controls)
    _assert_results_close(simulate_from_ir(toolpath),
                          simulate_columnar(ColumnarToolpath.from_toolpath(toolpath)))


def _feature_rich_design():
    'A design exercising arcs, extruder toggles, geometry changes and stationary extrusion.'
    return [
        fc.ExtrusionGeometry(area_model='rectangle', width=0.4, height=0.2),
        fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
        fc.Point(x=20, y=0, z=0.2),
        fc.Arc(centre=fc.Point(x=20, y=10), end=fc.Point(x=20, y=20), direction='anticlockwise'),
        fc.ExtrusionGeometry(width=0.6),  # widen mid-print
        fc.Point(x=0, y=20, z=0.2),
        fc.Extruder(on=False),
        fc.Point(x=0, y=0, z=0.4),  # travel
        fc.StationaryExtrusion(volume=5.0, speed=200),
        fc.Extruder(on=True),
        fc.Point(x=20, y=0, z=0.4),
    ]


def test_resolve_columnar_columns_match_object_resolve_field_by_field():
    """The direct columnar resolve (a second sequential walk) must stay pinned to the canonical
    object resolve - same Segments, same per-field values - or simulate() would silently drift."""
    steps = _feature_rich_design()
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    from fullcontrol.ir import resolve
    obj_segs = [e for e in resolve(steps, controls).events if isinstance(e, Segment)]
    col = resolve_columnar(steps, controls)
    assert col.n_segments == len(obj_segs)
    for i, seg in enumerate(obj_segs):
        assert col.travel[i] == seg.travel, f'seg {i} travel'
        assert col.speed[i] == seg.speed, f'seg {i} speed'
        assert abs(col.length[i] - seg.length) <= 1e-12, f'seg {i} length'
        assert abs(col.deposited_volume[i] - seg.deposited_volume) <= 1e-12, f'seg {i} vol'
        assert abs(col.filament_length[i] - seg.filament_length) <= 1e-12, f'seg {i} fil'
        assert col.source_index[i] == seg.source_index, f'seg {i} source_index'
        _w = None if np.isnan(col.width[i]) else col.width[i]
        _h = None if np.isnan(col.height[i]) else col.height[i]
        assert _w == seg.width, f'seg {i} width'
        assert _h == seg.height, f'seg {i} height'
    # stationary extrusion is aggregated into the material scalars
    assert abs(col.material_volume - 5.0) <= 1e-12


def test_resolve_columnar_simulate_matches_object_path_end_to_end():
    steps = _feature_rich_design()
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    from fullcontrol.ir import resolve
    obj = simulate_from_ir(resolve(steps, controls))
    col = simulate_columnar(resolve_columnar(steps, controls))
    _assert_results_close(obj, col)


def test_simulate_default_uses_columnar_fast_path_matching_object_path():
    steps = _feature_rich_design()
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    from fullcontrol.ir import resolve
    object_path = simulate_from_ir(resolve(steps, controls))
    public = fc.transform(steps, 'simulation', controls, show_tips=False)
    _assert_results_close(object_path, public)


def test_simulate_with_optimize_passes_falls_back_and_applies_passes():
    """merge_collinear collapses collinear moves; simulate must reflect that (fewer segments),
    proving it falls back to the object IR when passes are configured (the columnar path has none)."""
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=20, y=0, z=0.2), fc.Point(x=30, y=0, z=0.2)]
    plain = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    optimized = fc.GcodeControls(printer_name='generic',
                                 initialization_data={'nozzle_temp': 210, 'optimize': ['merge_collinear']})
    r_plain = fc.transform(steps, 'simulation', plain, show_tips=False)
    r_opt = fc.transform(steps, 'simulation', optimized, show_tips=False)
    assert r_opt.segment_count < r_plain.segment_count
    # the merged path still deposits the same material and takes the same time
    assert abs(r_opt.extruded_volume - r_plain.extruded_volume) <= 1e-6
    assert abs(r_opt.total_time_s - r_plain.total_time_s) <= 1e-6


def test_empty_toolpath_columnar_fold():
    c = ColumnarToolpath.from_toolpath(Toolpath([]))
    r = simulate_columnar(c)
    assert r.segment_count == 0
    assert r.total_time_s == 0.0
    assert r.max_flow_rate == 0.0
