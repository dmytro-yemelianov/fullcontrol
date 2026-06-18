"""Client-side parse -> simulate parity (Phase 6, WASM integration).

The browser pipeline is `parse_gcode(text) -> IR JSON` then `simulate_from_ir(IR JSON) -> the nine
simulation metrics`, both running entirely in the Rust kernel (wasm in the browser, the identical
shared helper in `metrics.rs` here). This suite pins that pipeline against the canonical Python
simulation: parsing the g-code a design emits and simulating the parsed IR must reproduce the same
metrics as `fc.transform(steps, 'simulation')` for that design.

Both `parse_gcode` and `simulate_from_ir` are exercised through the *compiled extension's raw
functions* (`fullcontrol_kernel.parse_gcode` / `.simulate_from_ir`) - exactly the JSON-string ABI
the wasm build exposes to JavaScript - so this is a faithful stand-in for the headless-browser test.

The compiled extension is optional - `pytest.importorskip` keeps CI without it green.
"""
import json

import pytest

_kernel = pytest.importorskip('fullcontrol_kernel')

import fullcontrol as fc  # noqa: E402
from fullcontrol.gcode.state import State  # noqa: E402
from fullcontrol.gcode.dialect import gcode_from_ir  # noqa: E402
from fullcontrol.ir import resolve  # noqa: E402
from fullcontrol.ir.serialize import from_json  # noqa: E402
from fullcontrol.gcode_engine import ParseParams  # noqa: E402
from fullcontrol.simulate.run import simulate_from_ir as py_simulate_from_ir  # noqa: E402


_METRIC_FIELDS = [
    'total_time_s', 'print_time_s', 'travel_time_s', 'extruding_distance',
    'travel_distance', 'extruded_volume', 'filament_length', 'segment_count', 'max_flow_rate',
]


def _emit_full(steps, controls):
    'The full pure-Python gcode (procedures + motion), exactly as fc.transform(...,"gcode").'
    controls.initialize()
    dstate = State(steps, controls)
    toolpath = resolve(steps, controls, state=dstate)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


def _params_json(params):
    'The same JSON ABI `fullcontrol.ir.kernel.parse_gcode_rust` hands the Rust/wasm parser.'
    return json.dumps({
        'flavor': params.flavor,
        'relative_e': params.relative_e,
        'e_units': params.e_units,
        'dia_feed': params.dia_feed,
        'travel_g1_e0': params.travel_g1_e0,
    })


def _kernel_parse_simulate(gcode, params):
    '''The exact client-side pipeline: kernel.parse_gcode(text) -> IR JSON string, then
    kernel.simulate_from_ir(IR JSON) -> the nine-tuple of metrics, decoded into a dict.'''
    ir_json = _kernel.parse_gcode(gcode, _params_json(params))
    metrics = _kernel.simulate_from_ir(ir_json)
    return dict(zip(_METRIC_FIELDS, metrics))


# --- designs (cover linear, travel, arcs, helical, stationary, abs-E, klipper) ---------------

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
    'helical_arc': (_helical_arc, {}),
    'stationary': (_stationary, {}),
    'abs_e_square': (_square, {'relative_e': False}),
    'klipper_square': (_square, {'gcode_flavor': 'klipper'}),
    'g1_e0_travel': (_with_travel, {'travel_format': 'G1_E0'}),
}


# `fc.transform(steps,'simulation')` simulates the design directly; this pipeline first emits the
# g-code and parses it back, so the end-to-end comparison only holds where the round-trip is
# loss-free. Two designs are excluded from it (their lossy round-trip is a *parser* property, fully
# covered by the kernel-vs-Python `simulate_from_ir` fold-parity test below, which folds the SAME
# parsed IR through both backends for every design):
#   - g1_e0_travel: `G1 ... E0` for an off-extruder move is indistinguishable on re-parse from an
#     extruding move whose delta-E rounds to zero, so the parser classifies it as extruding.
#   - stationary: StationaryExtrusion emits a `G1 F.. E..` line with no XYZ; on re-parse that is a
#     zero-length move, so the stationary material volume is not recovered as a MaterialEvent.
_END_TO_END = [n for n in _DESIGNS if n not in ('g1_e0_travel', 'stationary')]


@pytest.mark.parametrize('name', list(_DESIGNS))
def test_kernel_simulate_from_ir_matches_python_fold(name):
    '''The kernel `simulate_from_ir` (the wasm fold) equals the Python `simulate_from_ir` over the
    SAME IR document. Both backends run the identical sequential fold on the IR the Rust parser
    produced (decoded into a Toolpath for the Python side), so this isolates the fold itself. The
    only difference possible is the last bit or two: `serde_json` and CPython's `json` can round a
    given decimal literal differently when re-parsing the IR's numeric strings, which then propagates
    through the accumulating sums - hence a tight ULP-scale tolerance rather than bit-exact.'''
    factory, init = _DESIGNS[name]
    steps = factory()
    gcode = _emit_full(steps, _controls(**init))
    params = ParseParams.from_controls(_controls(**init))

    ir_json = _kernel.parse_gcode(gcode, _params_json(params))
    got = dict(zip(_METRIC_FIELDS, _kernel.simulate_from_ir(ir_json)))

    # Decode the very same IR JSON into a Toolpath and fold it with the reference Python backend.
    ref = py_simulate_from_ir(from_json(ir_json))

    assert got['segment_count'] == ref.segment_count and got['segment_count'] > 0
    for field in _METRIC_FIELDS:
        g = got[field]
        r = getattr(ref, field)
        assert g == pytest.approx(r, rel=1e-12, abs=1e-12), (
            f'{name}.{field}: kernel={g!r} python={r!r}')


@pytest.mark.parametrize('name', _END_TO_END)
def test_kernel_parse_simulate_matches_python_simulation(name):
    '''End-to-end: the wasm/browser pipeline (parse_gcode + simulate_from_ir) reproduces the canonical
    `fc.transform(steps, "simulation")` metrics. Tolerance reflects the g-code's 6-decimal E word: the
    parser reconstructs deposited volume from the rounded E value, so volumes/flow differ by ~1e-5.'''
    factory, init = _DESIGNS[name]
    steps = factory()

    gcode = _emit_full(steps, _controls(**init))
    params = ParseParams.from_controls(_controls(**init))
    got = _kernel_parse_simulate(gcode, params)

    ref = fc.transform(steps, 'simulation', _controls(**init))

    assert got['segment_count'] == ref.segment_count, f'segment_count mismatch: {got} vs {ref}'
    assert got['segment_count'] > 0
    for field in _METRIC_FIELDS:
        if field == 'segment_count':
            continue
        g = got[field]
        r = getattr(ref, field)
        # times/distances are exact; deposited-volume-derived metrics carry the E-word rounding.
        assert g == pytest.approx(r, rel=1e-4, abs=1e-4), (
            f'{name}.{field}: kernel={g!r} python={r!r}')


def test_simulate_from_ir_empty_ir():
    'A trivial IR (no events) folds to all-zero metrics without error.'
    metrics = dict(zip(_METRIC_FIELDS, _kernel.simulate_from_ir('{"version": 1, "events": []}')))
    assert metrics['segment_count'] == 0
    assert metrics['total_time_s'] == 0.0
