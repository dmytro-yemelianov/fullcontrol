"""Rust <-> Python g-code parser parity (Phase 2).

The Rust g-code parser (`rust_kernel/src/parser.rs`, exposed as `fullcontrol_kernel.parse_gcode`)
is a field-by-field port of the pure-Python reference parser
(`fullcontrol.gcode_engine.parser._parse_gcode_python`). This suite pins that parity: for several
g-code fixtures - linear, arcs, relative-E and absolute-E - the Rust parser's IR must equal the
Python parser's IR **field-by-field** (compared as rebuilt Toolpath events, not as raw JSON
strings, since serde key order may differ). A re-emit round-trip is also asserted: re-emitting the
Rust-parsed Toolpath produces the same g-code as re-emitting the Python-parsed one.

The compiled extension is optional - `pytest.importorskip` keeps CI without it green.
"""
import pytest

pytest.importorskip('fullcontrol_kernel')

import fullcontrol as fc  # noqa: E402
from fullcontrol.gcode.state import State  # noqa: E402
from fullcontrol.gcode.dialect import gcode_from_ir  # noqa: E402
from fullcontrol.ir import resolve  # noqa: E402
from fullcontrol.ir.serialize import to_json, from_json  # noqa: E402
from fullcontrol.ir.kernel import parse_gcode_rust  # noqa: E402
from fullcontrol.gcode_engine import ParseParams  # noqa: E402
from fullcontrol.gcode_engine.parser import _parse_gcode_python  # noqa: E402


# --- helpers -------------------------------------------------------------------------------

def _emit_full(steps, controls):
    'The full pure-Python gcode (procedures + motion), exactly as fc.transform(...,"gcode").'
    controls.initialize()
    dstate = State(steps, controls)
    toolpath = resolve(steps, controls, state=dstate)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


def _reemit(toolpath, controls):
    'Re-emit a parsed Toolpath through the same pure-Python dialect.'
    controls.initialize()
    dstate = State([], controls, procedures=False)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


def _normalise(toolpath):
    '''Rebuild a Toolpath through the JSON round-trip so both the Python and Rust sides go through
    the same `from_json` registry. This makes the event objects directly comparable (Segments and
    MaterialEvents compare by value; pass-through steps become the same fc.* classes).'''
    return from_json(to_json(toolpath))


# --- designs -------------------------------------------------------------------------------

def _square():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
            fc.Point(x=10, y=0), fc.Point(x=10, y=10),
            fc.Point(x=0, y=10), fc.Point(x=0, y=0)]


def _with_travel():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Extruder(on=False), fc.Point(x=20, y=0),
            fc.Extruder(on=True), fc.Point(x=20, y=10), fc.Point(x=10, y=10)]


def _with_arc_cw():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Arc(centre=fc.Point(x=10, y=5), end=fc.Point(x=10, y=10), direction='clockwise'),
            fc.Point(x=0, y=10)]


def _with_arc_ccw():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Arc(centre=fc.Point(x=10, y=5), end=fc.Point(x=10, y=10), direction='anticlockwise'),
            fc.Point(x=0, y=10)]


def _helical_arc():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Arc(centre=fc.Point(x=10, y=5), end=fc.Point(x=10, y=10, z=0.6),
                   direction='clockwise')]


def _stationary():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.StationaryExtrusion(volume=5, speed=200), fc.Point(x=20, y=0)]


def _controls(**init):
    base = {'print_speed': 1000, 'travel_speed': 2000}
    base.update(init)
    return fc.GcodeControls(printer_name='generic', initialization_data=base)


_DESIGNS = {
    'square': (_square, {}),
    'with_travel': (_with_travel, {}),
    'arc_cw': (_with_arc_cw, {}),
    'arc_ccw': (_with_arc_ccw, {}),
    'helical_arc': (_helical_arc, {}),
    'stationary': (_stationary, {}),
    'abs_e_square': (_square, {'relative_e': False}),
    'abs_e_arc': (_with_arc_cw, {'relative_e': False}),
    'klipper_square': (_square, {'gcode_flavor': 'klipper'}),
    'g1_e0_travel': (_with_travel, {'travel_format': 'G1_E0'}),
}


@pytest.mark.parametrize('name', list(_DESIGNS))
def test_rust_python_parser_parity(name):
    'The Rust parser produces the SAME IR as the Python parser, field-by-field.'
    factory, init = _DESIGNS[name]
    steps = factory()
    controls = _controls(**init)
    gcode = _emit_full(steps, controls)
    params = ParseParams.from_controls(_controls(**init))

    py_tp = _normalise(_parse_gcode_python(gcode, params))
    rust_tp = parse_gcode_rust(gcode, params)
    assert rust_tp is not None, 'kernel.parse_gcode unexpectedly unavailable'

    assert len(py_tp.events) == len(rust_tp.events)
    for i, (a, b) in enumerate(zip(py_tp.events, rust_tp.events)):
        assert type(a) is type(b), f'event {i}: {type(a).__name__} != {type(b).__name__}'
        assert a == b, f'event {i} differs:\n  py  ={a!r}\n  rust={b!r}'


@pytest.mark.parametrize('name', list(_DESIGNS))
def test_rust_python_reemit_parity(name):
    're-emitting the Rust-parsed Toolpath == re-emitting the Python-parsed one (byte-identical).'
    factory, init = _DESIGNS[name]
    steps = factory()
    controls = _controls(**init)
    gcode = _emit_full(steps, controls)
    params = ParseParams.from_controls(_controls(**init))

    py_tp = _parse_gcode_python(gcode, params)
    rust_tp = parse_gcode_rust(gcode, params)
    assert rust_tp is not None

    py_out = _reemit(py_tp, _controls(**init))
    rust_out = _reemit(rust_tp, _controls(**init))
    assert rust_out == py_out
    # and both reproduce the original g-code byte-for-byte (the parser's round-trip discipline)
    assert rust_out == gcode


def test_rust_parser_default_params():
    'Parsing with detected params (no explicit ParseParams) matches the Python parser.'
    steps = _square()
    controls = _controls()
    gcode = _emit_full(steps, controls)
    params = ParseParams.detect(gcode)

    py_tp = _normalise(_parse_gcode_python(gcode, params))
    rust_tp = parse_gcode_rust(gcode, params)
    assert [type(e).__name__ for e in rust_tp.events] == [type(e).__name__ for e in py_tp.events]
    for a, b in zip(py_tp.events, rust_tp.events):
        assert a == b
