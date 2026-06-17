"""Conformance contract for the Rust columnar-resolve microkernel.

Skips cleanly when the compiled extension is not present (so CI without the crate built stays
green). When present, pins the Rust-backed columnar result FIELD-BY-FIELD to the canonical
Python `resolve_columnar`, and checks the wrapper falls back (returns None) on an Arc design.
"""
import numpy as np
import pytest

import fullcontrol as fc
from fullcontrol.gcode.controls import GcodeControls
from fullcontrol.ir.columnar import resolve_columnar

pytest.importorskip("fullcontrol_kernel")
from fullcontrol.ir.kernel import resolve_columnar_rust  # noqa: E402


def _controls():
    return GcodeControls(printer_name="generic")


def _linear_design():
    'A linear design: points + extruder toggles + geometry change + stationary + speed change.'
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


def test_rust_matches_python_field_by_field():
    steps = _linear_design()
    py = resolve_columnar(steps, _controls())
    rs = resolve_columnar_rust(steps, _controls())

    assert rs is not None, "wrapper should use the Rust kernel for a linear design"
    assert rs.n_segments == py.n_segments

    np.testing.assert_allclose(rs.start, py.start, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(rs.end, py.end, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_array_equal(rs.travel, py.travel)
    np.testing.assert_allclose(rs.speed, py.speed, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(rs.length, py.length, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(rs.deposited_volume, py.deposited_volume, rtol=0, atol=1e-9,
                               equal_nan=True)
    np.testing.assert_allclose(rs.filament_length, py.filament_length, rtol=0, atol=1e-9,
                               equal_nan=True)
    np.testing.assert_array_equal(rs.source_index, py.source_index)
    np.testing.assert_allclose(rs.width, py.width, rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(rs.height, py.height, rtol=0, atol=1e-9, equal_nan=True)

    assert rs.material_volume == pytest.approx(py.material_volume, abs=1e-9)
    assert rs.material_filament == pytest.approx(py.material_filament, abs=1e-9)


def test_rust_falls_back_on_arc():
    steps = [
        fc.Point(x=0, y=0, z=0.2),
        fc.Extruder(on=True),
        fc.Point(x=10, y=0, z=0.2),
        fc.Arc(end=fc.Point(x=20, y=0, z=0.2), centre=fc.Point(x=15, y=0, z=0.2),
               direction="clockwise"),
        fc.Point(x=30, y=0, z=0.2),
    ]
    assert resolve_columnar_rust(steps, _controls()) is None
