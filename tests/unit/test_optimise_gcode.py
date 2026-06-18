"""Phase-4 optimisation passes + `fc.optimise_gcode` (TDD invariants).

Each new IR->IR pass (`arc_fit`, `travel_reorder`, `adaptive_speed`, `simplify`) is pinned to the
invariant the plan states, and `optimise_gcode` is pinned to its end-to-end contract: parse ->
optimise -> re-emit g-code that re-parses cleanly and (for material-preserving passes) carries the
same physical material as the input. All emission/parse uses the pure-Python dialect/parser.
"""
import math

import pytest

import fullcontrol as fc
from fullcontrol.ir import resolve, Segment
from fullcontrol.gcode_engine import parse_gcode, ParseParams, optimise_gcode, OptimisationReport
from fullcontrol.gcode_engine.passes.arc_fit import arc_fit
from fullcontrol.gcode_engine.passes.travel_reorder import travel_reorder
from fullcontrol.gcode_engine.passes.adaptive_speed import adaptive_speed
from fullcontrol.gcode_engine.passes.simplify import simplify
from fullcontrol.simulate.run import simulate_from_ir


def _controls(**init):
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'primer': 'no_primer', **init})


def _extruding(toolpath):
    return [e for e in toolpath.events if isinstance(e, Segment) and not e.travel]


def _extrude_volume(toolpath):
    return sum(s.deposited_volume for s in _extruding(toolpath))


# --------------------------------------------------------------------------- #
# arc_fit
# --------------------------------------------------------------------------- #

def _tessellated_circle(n=64, r=10.0, cx=20.0, cy=20.0, full=True):
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2),
             fc.Point(x=cx + r, y=cy, z=0.2), fc.Extruder(on=True)]
    last = n if full else n
    span = 2 * math.pi if full else math.pi
    for i in range(1, last + 1):
        a = span * i / n
        steps.append(fc.Point(x=cx + r * math.cos(a), y=cy + r * math.sin(a)))
    return steps


def test_arc_fit_merges_circle_conserves_material():
    tp = resolve(_tessellated_circle(n=64), _controls())
    before = sum(1 for s in _extruding(tp))
    vol_before = _extrude_volume(tp)

    out = arc_fit(tp, tolerance=0.05)
    arcs = [e for e in out.events if isinstance(e, Segment) and e.kind == 'arc']

    assert before == 64
    assert len(arcs) == 1, 'the tessellated circle should collapse to a single arc'
    assert abs(_extrude_volume(out) - vol_before) <= 1e-6, 'arc_fit must conserve deposited volume'


def test_arc_fit_reemits_as_g2_g3():
    tp = resolve(_tessellated_circle(n=32, full=False), _controls())  # half circle
    out = arc_fit(tp, tolerance=0.05)
    text = _reemit(out)
    assert ('G2' in text) or ('G3' in text), 'a merged arc must re-emit as a G2/G3 move'


def test_arc_fit_leaves_tight_curve_as_lines():
    'A tiny-radius circle (< 0.5 mm) stays as line segments.'
    tp = resolve(_tessellated_circle(n=24, r=0.3, cx=5, cy=5), _controls())
    out = arc_fit(tp, tolerance=0.05)
    arcs = [e for e in out.events if isinstance(e, Segment) and e.kind == 'arc']
    assert arcs == [], 'tight curves should be left as lines'


# --------------------------------------------------------------------------- #
# travel_reorder
# --------------------------------------------------------------------------- #

def _three_islands_bad_order():
    'Three squares visited far -> very-far -> near: a deliberately wasteful travel order.'
    def square(ox, oy):
        return [fc.Extruder(on=False), fc.Point(x=ox, y=oy, z=0.2), fc.Extruder(on=True),
                fc.Point(x=ox + 5, y=oy), fc.Point(x=ox + 5, y=oy + 5),
                fc.Point(x=ox, y=oy + 5), fc.Point(x=ox, y=oy)]
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2)]
    steps += square(0, 0) + square(100, 0) + square(10, 0)
    return steps


def test_travel_reorder_reduces_travel():
    tp = resolve(_three_islands_bad_order(), _controls())
    travel_before = simulate_from_ir(tp).travel_distance
    out = travel_reorder(tp)
    travel_after = simulate_from_ir(out).travel_distance
    assert travel_after < travel_before, 'travel_reorder must strictly reduce total travel'


def test_travel_reorder_preserves_island_internals_and_material():
    tp = resolve(_three_islands_bad_order(), _controls())
    out = travel_reorder(tp)
    # same extruding-segment geometry set (island internals unchanged, only order of islands)
    before = sorted((str(s.start), str(s.end)) for s in _extruding(tp))
    after = sorted((str(s.start), str(s.end)) for s in _extruding(out))
    assert before == after, 'island internal segments must be unchanged'
    assert abs(_extrude_volume(out) - _extrude_volume(tp)) <= 1e-9


def test_travel_reorder_no_cross_layer():
    'Two layers, each with two islands: the layer order must be preserved (no z interleave).'
    def square(ox, oy, z):
        return [fc.Extruder(on=False), fc.Point(x=ox, y=oy, z=z), fc.Extruder(on=True),
                fc.Point(x=ox + 5, y=oy), fc.Point(x=ox + 5, y=oy + 5), fc.Point(x=ox, y=oy + 5)]
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2)]
    steps += square(0, 0, 0.2) + square(50, 0, 0.2)
    steps += square(0, 0, 0.4) + square(50, 0, 0.4)
    tp = resolve(steps, _controls())
    out = travel_reorder(tp)
    zs = [round(s.end[2], 3) for s in _extruding(out)]
    # all layer-0.2 extrudes precede all layer-0.4 extrudes (monotone, no interleaving)
    assert zs == sorted(zs), 'no cross-layer reordering allowed'


# --------------------------------------------------------------------------- #
# adaptive_speed
# --------------------------------------------------------------------------- #

def test_adaptive_speed_lowers_corner_speed():
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Point(x=0, y=0, z=0.2),
             fc.Extruder(on=True), fc.Point(x=10, y=0), fc.Point(x=10, y=10)]  # 90deg corner
    tp = resolve(steps, _controls())
    orig = _extruding(tp)
    out = adaptive_speed(tp, corner_factor=0.7, min_speed=100, max_speed=12000)
    new = _extruding(out)
    assert new[1].speed < orig[1].speed, 'the corner segment speed must be lowered'
    assert all(a.deposited_volume == b.deposited_volume for a, b in zip(orig, new)), \
        'adaptive_speed must not change deposited material'


def test_adaptive_speed_clamps_to_min():
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Point(x=0, y=0, z=0.2),
             fc.Extruder(on=True), fc.Point(x=10, y=0), fc.Point(x=0, y=0)]  # 180deg hairpin
    tp = resolve(steps, _controls())
    out = adaptive_speed(tp, corner_factor=0.1, min_speed=900, max_speed=12000)
    speeds = [s.speed for s in _extruding(out)]
    assert min(speeds) >= 900, 'speeds must be clamped to min_speed'


# --------------------------------------------------------------------------- #
# simplify
# --------------------------------------------------------------------------- #

def test_simplify_merges_collinear_run_conserves_material():
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Point(x=0, y=0, z=0.2),
             fc.Extruder(on=True)]
    for i in range(1, 11):
        steps.append(fc.Point(x=i, y=0.001 * (i % 2)))  # nearly-collinear, deviation < 0.01
    tp = resolve(steps, _controls())
    before = len(_extruding(tp))
    vol_before = _extrude_volume(tp)
    out = simplify(tp, tolerance=0.01)
    after = len(_extruding(out))
    assert after < before, 'redundant collinear points must be removed'
    assert abs(_extrude_volume(out) - vol_before) <= 1e-9, 'simplify must conserve material'


def test_simplify_respects_tolerance():
    'A vertex that deviates more than tolerance is kept (not flattened away).'
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Point(x=0, y=0, z=0.2),
             fc.Extruder(on=True), fc.Point(x=5, y=2), fc.Point(x=10, y=0)]  # a clear 2 mm peak
    tp = resolve(steps, _controls())
    out = simplify(tp, tolerance=0.01)
    assert len(_extruding(out)) == 2, 'a >tolerance vertex must be preserved'


# --------------------------------------------------------------------------- #
# optimise_gcode (end-to-end)
# --------------------------------------------------------------------------- #

_GCODE = """M83
G1 F1000 X10 Y0 E0.1
G1 X20 Y0 E0.1
G1 X30 Y0 E0.1
G1 X30 Y10 E0.1
"""


def test_optimise_gcode_returns_text_and_report():
    out, report = optimise_gcode(_GCODE)
    assert isinstance(out, str) and out.strip()
    assert isinstance(report, OptimisationReport)
    assert report.passes, 'a report must record at least one pass'
    assert report.passes[0].segments_after <= report.passes[0].segments_before


def test_optimise_gcode_output_reparses_and_conserves_material():
    out, report = optimise_gcode(_GCODE)
    p = ParseParams.detect(_GCODE)
    tp_in = parse_gcode(_GCODE, p)
    tp_out = parse_gcode(out, p)  # must not raise
    assert tp_out.events, 'optimised output must re-parse to a non-empty toolpath'
    si = simulate_from_ir(tp_in)
    so = simulate_from_ir(tp_out)
    assert so.filament_length == pytest.approx(si.filament_length, abs=1e-3)
    assert so.extruded_volume == pytest.approx(si.extruded_volume, abs=1e-3)


def test_optimise_gcode_return_report_false():
    out = optimise_gcode(_GCODE, return_report=False)
    assert isinstance(out, str)


def test_optimise_gcode_explicit_passes():
    out, report = optimise_gcode(_GCODE, passes=['simplify'])
    assert [p.name for p in report.passes] == ['simplify']


def test_optimise_gcode_unknown_pass_raises():
    with pytest.raises(ValueError):
        optimise_gcode(_GCODE, passes=['does_not_exist'])


def test_optimise_gcode_arc_fit_end_to_end_emits_arc():
    'A circle emitted to g-code, optimised with arc_fit, re-emits with a G2/G3 arc.'
    steps = _tessellated_circle(n=48, full=False)
    text = _emit_motion(steps)
    out, report = optimise_gcode(text, passes=['arc_fit'])
    assert ('G2' in out) or ('G3' in out)
    p = ParseParams.detect(text)
    assert simulate_from_ir(parse_gcode(out, p)).extruded_volume == pytest.approx(
        simulate_from_ir(parse_gcode(text, p)).extruded_volume, rel=1e-3)


# --------------------------------------------------------------------------- #
# helpers (emit / re-emit through the pure-Python dialect)
# --------------------------------------------------------------------------- #

def _emit_motion(steps):
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.dialect import gcode_from_ir
    controls = _controls()
    controls.initialize()
    dstate = State(steps, controls)
    tp = resolve(steps, controls, include_procedures=False, state=dstate)
    gcode_from_ir(tp, dstate)
    return '\n'.join(dstate.gcode)


def _reemit(toolpath):
    from fullcontrol.gcode.state import State
    from fullcontrol.gcode.dialect import gcode_from_ir
    controls = _controls()
    controls.initialize()
    dstate = State([], controls, procedures=False)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)
