"""The Fractional Design Engine (Polar) gallery design - faithful reimplementation tests.

Mirrors tests/unit/test_examples.py: the design must resolve to g-code, simulate to a real print
(time / volume > 0) and validate clean on a generous build volume. On top of that we assert the
*polar structure* of the engine: a k-petal rose has 2k radial maxima around the centre, fractional
`turns` produce the expected angular span, and explicit radii / angle lists land exactly at those
polar coordinates (the original model's behaviour).
"""
import math

import numpy as np
import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.fractional_design_engine import fractional_design_engine

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

_CENTRE = (50.0, 50.0)


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data=dict(_BUILD))


def _points(steps):
    return [s for s in steps if isinstance(s, Point)]


def _radii(steps, centre=_CENTRE):
    cx, cy = centre
    return np.array([math.hypot(p.x - cx, p.y - cy) for p in _points(steps)])


def _radial_maxima(steps, centre=_CENTRE, tol=0.98):
    """Count radial maxima around the centre as a circular signal (closure-duplicate aware)."""
    r = _radii(steps, centre)
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]                                   # drop the loop-closing duplicate point
    near = r >= tol * r.max()
    circ = np.concatenate([near, [near[0]]])
    return int(np.sum(circ[:-1] & ~np.roll(circ[:-1], 1)))


# --- backend smoke + sanity (mirrors test_examples.py) ----------------------------------------

def test_starts_with_its_own_extrusion_geometry():
    steps = fractional_design_engine()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width and steps[0].height


def test_generates_gcode():
    gcode = fc.transform(fractional_design_engine(petals=5), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20
    assert 'G1' in gcode


def test_simulates_to_a_real_print():
    r = fc.transform(fractional_design_engine(petals=5), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0
    assert r.extruding_distance > 0


def test_validates_without_errors():
    r = fc.transform(fractional_design_engine(petals=5), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


# --- key geometry: the polar structure --------------------------------------------------------

@pytest.mark.parametrize('petals', [3, 4, 5, 6])
def test_rose_has_2k_radial_maxima(petals):
    """A k-petal rose r = radius*|cos(k*theta)| has 2k radial maxima over one full turn."""
    steps = fractional_design_engine(petals=petals, radius=20, points=1441, close=False)
    assert _radial_maxima(steps) == 2 * petals


def test_rose_stays_within_radius():
    radius = 18.0
    steps = fractional_design_engine(petals=5, radius=radius, points=600)
    r = _radii(steps)
    assert r.max() <= radius + 1e-6
    assert abs(r.max() - radius) < 1e-6              # a petal tip actually reaches full radius


@pytest.mark.parametrize('turns,expected_span', [(0.25, 0.5 * math.pi), (0.5, math.pi),
                                                 (1.0, 2 * math.pi), (1.5, 3 * math.pi)])
def test_fractional_turns_set_angular_span(turns, expected_span):
    """Fractional `turns` sweep exactly `turns * 2*pi` of cumulative polar angle."""
    cx, cy = _CENTRE
    steps = fractional_design_engine(petals=2, turns=turns, points=400, close=False)
    pts = _points(steps)
    # cumulative unwrapped angle from the (cx, cy) centre
    raw = np.array([math.atan2(p.y - cy, p.x - cx) for p in pts])
    span = float(np.unwrap(raw)[-1] - np.unwrap(raw)[0])
    assert abs(abs(span) - expected_span) < 1e-6


def test_explicit_lists_land_at_polar_coords():
    """Explicit angle/radial fraction lists reproduce the reference model's points exactly.

    These are the parameters baked into fractional-design-engine-polar.gcode (model a72616):
    the 11-point alternating 5-point star over one full turn.
    """
    radius = 20.0
    angle_fractions = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    radial_fractions = [1, 0.5, 1, 0.5, 1, 0.5, 1, 0.5, 1, 0.5, 1]
    steps = fractional_design_engine(radius=radius, centre=(50.0, 50.0),
                                     angle_fractions=angle_fractions,
                                     radial_fractions=radial_fractions, close=False)
    pts = _points(steps)
    assert len(pts) == len(angle_fractions)
    cx, cy = 50.0, 50.0
    for af, rf, p in zip(angle_fractions, radial_fractions, pts):
        theta = af * 2 * math.pi
        ex = cx + rf * radius * math.cos(theta)
        ey = cy + rf * radius * math.sin(theta)
        assert abs(p.x - ex) < 1e-6 and abs(p.y - ey) < 1e-6
    # spot-check against the literal g-code coordinates
    assert abs(pts[0].x - 70.0) < 1e-4 and abs(pts[0].y - 50.0) < 1e-4
    assert abs(pts[1].x - 58.0902) < 1e-3 and abs(pts[1].y - 55.8779) < 1e-3


def test_explicit_alternating_radii_create_a_star():
    """The alternating 1, 0.5 radial pattern gives 5 outer star tips at full radius."""
    radius = 20.0
    steps = fractional_design_engine(radius=radius,
                                     angle_fractions=[i / 10 for i in range(11)],
                                     radial_fractions=[1, 0.5] * 5 + [1], close=False)
    r = _radii(steps)
    assert _radial_maxima(steps) == 5                # five outer points of the star
    assert abs(r.max() - radius) < 1e-6
    assert abs(r.min() - 0.5 * radius) < 1e-6        # inner vertices at half radius


def test_layers_stack_flat():
    eh = 0.2
    steps = fractional_design_engine(petals=4, points=120, layers=3, extrusion_height=eh)
    zs = sorted({round(p.z, 6) for p in _points(steps)})
    assert zs == [0.0, eh, 2 * eh]                   # three distinct flat layers


def test_mismatched_lists_raise():
    with pytest.raises(ValueError):
        fractional_design_engine(angle_fractions=[0, 0.5], radial_fractions=[1])
    with pytest.raises(ValueError):
        fractional_design_engine(angle_fractions=[0, 0.5])  # only one list supplied
