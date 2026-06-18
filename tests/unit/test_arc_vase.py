"""The Arc Vase: a vase whose every layer is a closed loop of native ``fc.Arc`` (G2/G3) moves.

This is the gallery design that showcases FullControl's native arc capability: instead of hundreds
of short line segments per layer, each layer is just ``petals`` arc commands, climbing as one
helical spiral. These tests mirror tests/unit/test_examples.py (resolve -> simulate -> validate on a
200^3 build volume) and add the key assertion: the g-code really emits G2/G3 arc moves, and far
fewer of them than a segmented vase of the same fidelity would need.
"""
from math import hypot

import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.arc_vase import arc_vase

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

_CENTRE = (100.0, 100.0)


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data=_BUILD)


def _small():
    return arc_vase(petals=6, radius=22, scallop_depth=5, height=3, layer_height=0.3,
                    centre=_CENTRE)


def test_starts_with_its_own_extrusion_geometry():
    steps = _small()
    assert isinstance(steps, list)
    assert isinstance(steps[0], fc.ExtrusionGeometry)


def test_design_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20
    assert 'G1' in gcode                            # the primer / setup still uses linear moves


def test_design_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                     # material is actually deposited
    assert r.extruding_distance > 0


def test_design_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_gcode_emits_real_arc_moves_one_per_petal_per_layer():
    'THE KEY TEST: the layers are built from true G2/G3 arc moves - a handful per layer.'
    petals, height, layer_height = 6, 3.0, 0.3
    steps = arc_vase(petals=petals, height=height, layer_height=layer_height, scallop_depth=5,
                     centre=_CENTRE)
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    arc_lines = [ln for ln in gcode.splitlines() if ln.startswith(('G2 ', 'G3 '))]

    turns = round(height / layer_height)
    expected = petals * turns
    assert len(arc_lines) == expected               # exactly `petals` arc commands per layer

    # one arc step in the design -> one arc move in the g-code (no segmentation into G1 lines)
    assert len([s for s in steps if isinstance(s, fc.Arc)]) == expected

    # a segmented vase of the same smoothness would need ~100 segments per arc (the default arc
    # tessellation); the native-arc vase is dramatically smaller.
    segmented_equivalent = expected * 100
    assert len(arc_lines) < segmented_equivalent / 20


def test_convex_petals_emit_g2_concave_scallops_emit_g3():
    out = fc.transform(arc_vase(petals=6, height=1, bulge_out=True, centre=_CENTRE),
                       'gcode', _controls(), show_tips=False)
    inn = fc.transform(arc_vase(petals=6, height=1, bulge_out=False, centre=_CENTRE),
                       'gcode', _controls(), show_tips=False)
    assert any(ln.startswith('G2 ') for ln in out.splitlines())
    assert not any(ln.startswith('G3 ') for ln in out.splitlines())
    assert any(ln.startswith('G3 ') for ln in inn.splitlines())
    assert not any(ln.startswith('G2 ') for ln in inn.splitlines())


def test_helical_arcs_climb_so_the_vase_is_taller_than_one_layer():
    'Each arc advances z; the wall climbs as one continuous spiral (vase mode).'
    layer_height = 0.3
    steps = arc_vase(petals=6, height=4, layer_height=layer_height, centre=_CENTRE)
    arcs = [s for s in steps if isinstance(s, fc.Arc)]
    z_end = [a.end.z for a in arcs]
    assert z_end == sorted(z_end)                    # monotonically climbing
    assert z_end[-1] - z_end[0] > layer_height       # taller than a single layer
    # each arc carries a differing end-z (a true helical arc, not a flat ring then a z-hop)
    assert all(b > a for a, b in zip(z_end, z_end[1:]))


def test_cross_section_is_closed_and_petalled():
    'The arc endpoints (petal vertices) sit on the base radius and close back to the start.'
    radius, petals = 22.0, 6
    steps = arc_vase(petals=petals, radius=radius, height=1, scallop_depth=5, centre=_CENTRE)
    arcs = [s for s in steps if isinstance(s, fc.Arc)]
    cx, cy = _CENTRE
    # every arc end vertex lies on the nominal circle (radius), and the last vertex of a layer
    # returns to the first -> a closed loop
    for a in arcs:
        assert abs(hypot(a.end.x - cx, a.end.y - cy) - radius) < 1e-9
    start = next(s for s in steps if isinstance(s, Point))
    layer_end = arcs[petals - 1].end                 # end of the first full layer
    assert abs(layer_end.x - start.x) < 1e-9 and abs(layer_end.y - start.y) < 1e-9


def test_requires_at_least_two_petals():
    with pytest.raises(ValueError, match='petals'):
        arc_vase(petals=1)
