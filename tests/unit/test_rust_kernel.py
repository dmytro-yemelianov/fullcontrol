"""Conformance contract for the Rust microkernel (columnar resolve + fused simulate).

Skips cleanly when the compiled extension is not present (so CI without the crate built stays
green). When present, pins the Rust-backed columnar result FIELD-BY-FIELD to the canonical Python
`resolve_columnar` (including Arc designs, which the kernel now supports), and pins the fused
`simulate_rust` to `simulate_columnar`.
"""
import numpy as np
import pytest

import fullcontrol as fc
from fullcontrol.gcode.controls import GcodeControls
from fullcontrol.ir.columnar import resolve_columnar

pytest.importorskip("fullcontrol_kernel")
from fullcontrol.ir.kernel import resolve_columnar_rust, simulate_rust  # noqa: E402
from fullcontrol.simulate.run import simulate_columnar  # noqa: E402
from fullcontrol.ir.columnar import ColumnarToolpath  # noqa: E402


def _controls():
    return GcodeControls(printer_name="generic")


def _linear_design():
    'Points + extruder toggles + geometry change + stationary extrusion + speed change.'
    return [
        fc.Point(x=0, y=0, z=0.2),
        fc.Extruder(on=False),
        fc.Point(x=10, y=0, z=0.2),
        fc.Extruder(on=True),
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=10, y=10, z=0.2),
        fc.Point(x=0, y=10, z=0.2),
        fc.Printer(print_speed=2000, travel_speed=8000),
        fc.ExtrusionGeometry(width=0.8, height=0.3),
        fc.StationaryExtrusion(volume=5.0, speed=1000),
        fc.Point(x=0, y=0, z=0.2),
        fc.Extruder(on=False),
        fc.Point(x=5, y=5, z=0.4),
    ]


def _arc_design():
    'Same vocabulary but with G2/G3 arcs interleaved (now supported by the kernel).'
    return [
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=20, y=0, z=0.2),
        fc.Extruder(on=True),
        # two valid quarter arcs on radius 20 about the origin (each end is on the circle)
        fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
        fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=-20, y=0), direction='anticlockwise'),
        fc.Point(x=-20, y=10, z=0.4),
        fc.Extruder(on=False),
        fc.Point(x=0, y=0, z=0.4),
    ]


def _assert_columns_match(rs: ColumnarToolpath, py: ColumnarToolpath):
    assert rs is not None, "wrapper should use the Rust kernel"
    assert rs.n_segments == py.n_segments
    np.testing.assert_allclose(rs.start, py.start, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(rs.end, py.end, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_array_equal(rs.travel, py.travel)
    for field in ('speed', 'length', 'deposited_volume', 'filament_length', 'width', 'height'):
        np.testing.assert_allclose(getattr(rs, field), getattr(py, field), rtol=0, atol=1e-9,
                                   equal_nan=True, err_msg=field)
    np.testing.assert_array_equal(rs.source_index, py.source_index)
    assert rs.material_volume == pytest.approx(py.material_volume, abs=1e-9)
    assert rs.material_filament == pytest.approx(py.material_filament, abs=1e-9)


def test_rust_resolve_matches_python_linear():
    steps = _linear_design()
    _assert_columns_match(resolve_columnar_rust(steps, _controls()),
                          resolve_columnar(steps, _controls()))


def test_rust_resolve_matches_python_with_arcs():
    steps = _arc_design()
    _assert_columns_match(resolve_columnar_rust(steps, _controls()),
                          resolve_columnar(steps, _controls()))


def _assert_sim_close(rs, py):
    for field in ('total_time_s', 'print_time_s', 'travel_time_s', 'extruding_distance',
                  'travel_distance', 'extruded_volume', 'filament_length'):
        a, b = getattr(rs, field), getattr(py, field)
        assert a == 0 and b == 0 or abs(a - b) <= 1e-9 * max(abs(a), abs(b)), f'{field}: {a} vs {b}'
    assert rs.segment_count == py.segment_count
    assert rs.max_flow_rate == pytest.approx(py.max_flow_rate, rel=1e-12)


def test_rust_simulate_matches_python_linear():
    steps = _linear_design()
    _assert_sim_close(simulate_rust(steps, _controls()),
                      simulate_columnar(resolve_columnar(steps, _controls())))


def test_rust_simulate_matches_python_with_arcs():
    steps = _arc_design()
    _assert_sim_close(simulate_rust(steps, _controls()),
                      simulate_columnar(resolve_columnar(steps, _controls())))


def test_rust_simulate_matches_a_gallery_design():
    from examples import ripple_vase
    steps = ripple_vase(height=3, ripples_per_layer=12)
    _assert_sim_close(simulate_rust(steps, _controls()),
                      simulate_columnar(resolve_columnar(steps, _controls())))
