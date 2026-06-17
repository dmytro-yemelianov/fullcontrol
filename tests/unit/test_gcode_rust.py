"""Conformance: the Rust g-code engine's motion lines == the Python dialect's, byte-for-byte.

The Rust emitter (rust_kernel/src/gcode.rs) consumes the serialized IR (fullcontrol/ir/serialize)
and emits the G0/G1/G2/G3 + stationary-extrusion lines. These tests pin it to the Python dialect's
motion output on designs within its scope (no procedures, no retraction): linear moves, arcs,
relative and absolute E, and a MaterialEvent. Skips cleanly when the extension isn't built.
"""
import pytest

import fullcontrol as fc
from fullcontrol.gcode.state import State
from fullcontrol.gcode.dialect import gcode_from_ir
from fullcontrol.ir import resolve

pytest.importorskip("fullcontrol_kernel")
from fullcontrol.ir.kernel import emit_gcode_moves_rust, emit_gcode_rust  # noqa: E402


def _controls():
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'extrusion_width': 0.6, 'extrusion_height': 0.2})


def _assert_motion_matches(steps):
    controls = _controls()
    state = State(steps, controls, procedures=False)
    toolpath = resolve(steps, controls, include_procedures=False, initial_extruder_on=True, state=state)
    py_all = gcode_from_ir(toolpath, state)                 # mutates `state`'s E accumulator
    py_motion = [ln for ln in py_all if ln[:2] in ('G0', 'G1', 'G2', 'G3')]
    rel = state.extruder.relative_gcode is True
    tf = state.extruder.travel_format == 'G1_E0'
    rust = emit_gcode_moves_rust(toolpath, relative_e=rel, travel_g1_e0=tf)
    assert rust == py_motion
    assert len(rust) > 1
    return rust


def test_linear_design_absolute_e():
    from examples import spiral_vase
    _assert_motion_matches(spiral_vase(height=3, segments_per_layer=24, lobes=4))


def test_design_with_travels():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2),
             fc.Extruder(on=False), fc.Point(x=0, y=0, z=0.2),     # travel
             fc.Extruder(on=True), fc.Point(x=5, y=5, z=0.2)]
    _assert_motion_matches(steps)


def test_arcs():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=-20, y=0), direction='clockwise'),
             fc.Point(x=-20, y=10, z=0.4)]
    rust = _assert_motion_matches(steps)
    assert any(ln.startswith('G2') or ln.startswith('G3') for ln in rust)


def test_relative_e_mode():
    steps = [fc.Extruder(relative_gcode=True), fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    _assert_motion_matches(steps)


def test_stationary_extrusion_material_line():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
             fc.StationaryExtrusion(volume=5.0, speed=200), fc.Point(x=20, y=0, z=0.2)]
    rust = _assert_motion_matches(steps)
    assert any('F200' in ln for ln in rust)   # the material line carries the stationary speed


# --- full g-code (motion + procedures + the common non-motion commands) ---

def _assert_full_gcode_matches(steps, init):
    'The complete Rust file (with procedures) == fc.transform(steps, "gcode"), byte-for-byte.'
    controls = fc.GcodeControls(printer_name='generic', initialization_data=init)
    py = fc.transform(steps, 'gcode', controls, show_tips=False)
    dstate = State(steps, controls)
    toolpath = resolve(steps, controls, state=dstate)
    rel = dstate.extruder.relative_gcode is True
    tf = dstate.extruder.travel_format == 'G1_E0'
    rust = '\n'.join(emit_gcode_rust(toolpath, relative_e=rel, travel_g1_e0=tf))
    assert rust == py


def test_full_gcode_with_temps_and_fan():
    from examples import spiral_vase
    _assert_full_gcode_matches(spiral_vase(height=2, segments_per_layer=24, lobes=5),
                               {'nozzle_temp': 210, 'bed_temp': 50, 'fan_percent': 80})


def test_full_gcode_minimal():
    from examples import spiral_vase
    _assert_full_gcode_matches(spiral_vase(height=1.5, segments_per_layer=16), {'nozzle_temp': 210})


def test_full_gcode_arcs():
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2),
             fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
             fc.Point(x=0, y=30, z=0.2)]
    _assert_full_gcode_matches(steps, {'nozzle_temp': 215, 'bed_temp': 60})
