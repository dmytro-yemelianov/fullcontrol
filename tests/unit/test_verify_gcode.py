"""Phase-3 verification layer: fc.verify_gcode over parsed (lifted) g-code.

These tests trip individual rules with designs emitted to canonical FullControl g-code (the parser
only lifts canonical motion lines back to Segments), assert the no-false-positives property on our
own output for several gallery designs, and check the report shape (line numbers, simulation).
"""
import math

import pytest

import fullcontrol as fc
from fullcontrol.gcode_engine import verify_gcode, VerificationReport, Issue


def _gcode(steps, init):
    ctrl = fc.GcodeControls(printer_name='generic', initialization_data=init)
    g = fc.transform(steps, 'gcode', ctrl, show_tips=False)
    return g, fc.ParseParams.from_controls(ctrl)


# ---------------------------------------------------------------------------- report shape

def test_verify_returns_report_with_public_surface():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p)
    assert isinstance(rep, VerificationReport)
    assert hasattr(rep, 'errors') and hasattr(rep, 'warnings') and hasattr(rep, 'ok')
    assert isinstance(rep.summary(), str)
    # every Issue is an Issue dataclass
    assert all(isinstance(i, Issue) for i in rep.issues)


def test_verify_detects_params_when_omitted():
    g, _ = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g)  # no params -> detect
    assert rep.parse_params is not None


# ---------------------------------------------------------------------------- rule-by-rule

def test_cold_extrusion_is_an_error_with_a_line():
    # no nozzle_temp on generic -> no M104/M109 emitted -> extrusion before heating
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2),
                   fc.Point(x=30, y=20, z=0.2)], {})
    rep = verify_gcode(g, params=p, simulate=False)
    cold = [e for e in rep.errors if e.rule == 'cold_extrusion']
    assert cold, rep.summary()
    assert not rep.ok
    assert cold[0].line is not None and cold[0].line >= 1


def test_heated_gcode_has_no_cold_extrusion_error():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    assert not [e for e in rep.errors if e.rule == 'cold_extrusion']


def test_out_of_bounds_is_an_error_with_a_line_number():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, build_volume=(200, 200, 200), simulate=False)
    oob = [e for e in rep.errors if 'build volume' in e.message]
    assert oob, rep.summary()
    assert oob[0].line is not None and oob[0].segment_index is not None


def test_in_bounds_gcode_has_no_bounds_error():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=50, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, build_volume=(200, 200, 200), simulate=False)
    assert not [e for e in rep.errors if 'build volume' in e.message]


def test_flow_rate_ceiling_is_a_warning_with_segment_index():
    # wide/tall bead at high speed -> high volumetric flow
    steps = [fc.ExtrusionGeometry(width=2.0, height=1.0), fc.Printer(print_speed=6000),
             fc.Point(x=10, y=10, z=1.0), fc.Extruder(on=True), fc.Point(x=100, y=10, z=1.0)]
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False, max_flow_mm3s=15.0)
    flow = [w for w in rep.warnings if w.rule == 'flow_rate_ceiling']
    assert flow, rep.summary()
    assert flow[0].segment_index is not None and flow[0].line is not None


def test_flow_rate_ceiling_not_tripped_for_normal_print():
    steps = [fc.ExtrusionGeometry(width=0.4, height=0.2), fc.Printer(print_speed=1200),
             fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=10, z=0.2)]
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False, max_flow_mm3s=15.0)
    assert not [w for w in rep.warnings if w.rule == 'flow_rate_ceiling']


def test_arc_opportunity_is_info_on_a_circle():
    n = 20
    circle = [fc.Point(x=20 + 10 * math.cos(t / n * 2 * math.pi),
                       y=20 + 10 * math.sin(t / n * 2 * math.pi), z=0.2) for t in range(n + 1)]
    steps = [circle[0], fc.Extruder(on=True)] + circle[1:]
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    arcs = [i for i in rep.infos if i.rule == 'arc_opportunity']
    assert arcs, rep.summary()
    assert arcs[0].suggested_fix == 'arc_fit'


def test_arc_opportunity_not_tripped_for_a_straight_line():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=10, y=0, z=0.2), fc.Point(x=20, y=0, z=0.2),
             fc.Point(x=30, y=0, z=0.2), fc.Point(x=40, y=0, z=0.2),
             fc.Point(x=50, y=0, z=0.2), fc.Point(x=60, y=0, z=0.2)]
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    assert not [i for i in rep.infos if i.rule == 'arc_opportunity']


def test_cooling_sanity_warns_when_fan_off_after_first_layer():
    sq = [fc.Point(x=10, y=10, z=0.2), fc.Point(x=20, y=10, z=0.2),
          fc.Point(x=20, y=20, z=0.2), fc.Point(x=10, y=20, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    sq2 = [fc.Point(x=q.x, y=q.y, z=0.4) for q in sq]
    steps = [sq[0], fc.Extruder(on=True)] + sq[1:] + sq2
    g, p = _gcode(steps, {'nozzle_temp': 210, 'fan_percent': 0})
    rep = verify_gcode(g, params=p, simulate=False)
    cooling = [w for w in rep.warnings if w.rule == 'cooling_sanity']
    assert cooling, rep.summary()


def test_cooling_sanity_quiet_when_fan_on():
    sq = [fc.Point(x=10, y=10, z=0.2), fc.Point(x=20, y=10, z=0.2),
          fc.Point(x=20, y=20, z=0.2), fc.Point(x=10, y=20, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    sq2 = [fc.Point(x=q.x, y=q.y, z=0.4) for q in sq]
    steps = [sq[0], fc.Extruder(on=True)] + sq[1:] + sq2
    g, p = _gcode(steps, {'nozzle_temp': 210, 'fan_percent': 100})
    rep = verify_gcode(g, params=p, simulate=False)
    assert not [w for w in rep.warnings if w.rule == 'cooling_sanity']


def test_first_layer_adhesion_warns_when_first_layer_not_slowed():
    # constant speed across two layers -> first layer is not slowed
    sq = [fc.Point(x=10, y=10, z=0.2), fc.Point(x=30, y=10, z=0.2),
          fc.Point(x=30, y=30, z=0.2), fc.Point(x=10, y=30, z=0.2), fc.Point(x=10, y=10, z=0.2)]
    sq2 = [fc.Point(x=q.x, y=q.y, z=0.4) for q in sq]
    steps = [fc.Printer(print_speed=2000), sq[0], fc.Extruder(on=True)] + sq[1:] + sq2
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    adh = [w for w in rep.warnings if w.rule == 'first_layer_adhesion']
    assert adh, rep.summary()
    assert adh[0].line is not None


def test_travel_density_info_for_heavy_travel():
    # alternate tiny extrusions with long travels -> high travel/extrude ratio
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=1, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=80, y=0, z=0.2),
             fc.Extruder(on=True), fc.Point(x=81, y=0, z=0.2),
             fc.Extruder(on=False), fc.Point(x=0, y=80, z=0.2),
             fc.Extruder(on=True), fc.Point(x=1, y=80, z=0.2)]
    g, p = _gcode(steps, {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    td = [i for i in rep.infos if i.rule == 'travel_density']
    assert td, rep.summary()
    assert td[0].suggested_fix == 'travel_reorder'


# ---------------------------------------------------------------------------- simulation

def test_simulate_true_attaches_simulation_result():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=True)
    assert rep.simulation is not None
    assert rep.simulation.segment_count > 0
    assert rep.simulation.total_time_s > 0


def test_simulate_false_attaches_no_simulation():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=50, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, simulate=False)
    assert rep.simulation is None


# ---------------------------------------------------------------------------- provenance

def test_every_issue_from_parsing_has_a_one_based_line_or_none():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=10, z=0.2)],
                  {})
    rep = verify_gcode(g, params=p, build_volume=(200, 200, 200), simulate=False)
    for i in rep.issues:
        if i.line is not None:
            assert i.line >= 1


def test_raise_if_errors_raises():
    g, p = _gcode([fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=10, z=0.2)],
                  {'nozzle_temp': 210})
    rep = verify_gcode(g, params=p, build_volume=(200, 200, 200), simulate=False)
    with pytest.raises(ValueError, match='verification failed'):
        rep.raise_if_errors()


# ---------------------------------------------------------------------------- no false positives

@pytest.mark.parametrize('name', ['spiral_vase', 'ripple_vase', 'gyroid_infill',
                                  'twisted_polygon_vase', 'star_polygon_lattice'])
def test_no_false_positive_errors_on_our_own_gcode(name):
    from examples import GALLERY
    steps = GALLERY[name]()
    init = {'build_volume_x': 300, 'build_volume_y': 300, 'build_volume_z': 300,
            'nozzle_temp': 210, 'fan_percent': 100}
    g, p = _gcode(steps, init)
    rep = verify_gcode(g, params=p, build_volume=(300, 300, 300))
    # our own valid g-code must produce NO errors (warnings/infos are allowed)
    assert rep.ok, f'{name} spurious errors: {[(e.rule, e.message) for e in rep.errors]}'
    assert rep.simulation is not None and rep.simulation.segment_count > 0


def test_verify_gcode_is_exported_from_fc():
    assert hasattr(fc, 'verify_gcode')
    assert hasattr(fc, 'VerificationReport')
    assert hasattr(fc, 'Issue')
