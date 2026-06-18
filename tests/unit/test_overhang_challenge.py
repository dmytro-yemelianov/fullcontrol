"""The 'Overhang Challenge' gallery design must resolve cleanly through all four backends and prove
its defining feature: a wall that leans progressively OUTWARD with height (the overhang test), with a
'Plus' variant that swaps the circular cross-section for a polygonal one.

Mirrors tests/unit/test_examples.py: each variant is generated small and run to gcode, simulation and
validation (non-trivial length, material deposited, no validation errors against a generous build
volume), plus geometry asserts on the overhang profile and the Plus cross-section.
"""
import math

import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.overhang_challenge import overhang_challenge

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

# small-but-representative variants so the suite stays fast
_SMALL = {
    'base': lambda: overhang_challenge(segments_per_layer=40, base_rings=4),
    'plus': lambda: overhang_challenge(plus=True, segments_per_layer=40, base_rings=4),
    'plus_inward': lambda: overhang_challenge(plus=True, outward=False, segments_per_layer=40,
                                              base_rings=4),
}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _points(steps):
    return [s for s in steps if isinstance(s, Point)]


def _radius(p, cx=50.0, cy=50.0):
    return math.hypot(p.x - cx, p.y - cy)


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_generates_gcode(name):
    steps = _SMALL[name]()
    assert isinstance(steps[0], fc.ExtrusionGeometry)          # starts with its own geometry
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                              # a real toolpath, not a stub
    assert 'G1' in gcode                                       # extruding moves were emitted


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_simulates_to_a_real_print(name):
    steps = _SMALL[name]()
    r = fc.transform(steps, 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                               # material is actually deposited
    assert r.extruding_distance > 0


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_validates_without_errors(name):
    steps = _SMALL[name]()
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_footprint_and_height_match_the_real_models():
    'The real overhang-challenge.gcode is ~19.8 x 19.8 x 4.3 mm: a short, wide-footed object.'
    pts = _points(overhang_challenge())
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    assert 18 < (max(xs) - min(xs)) < 22                       # ~20 mm footprint (the foot disc)
    assert 18 < (max(ys) - min(ys)) < 22
    assert 3.5 < (max(zs) - min(zs)) < 5.0                     # ~4.3 mm tall


def test_wall_overhangs_outward_and_increases_monotonically_with_height():
    '''The defining feature: above the straight wall the radius grows with z, so the wall leans
    progressively outward - the radius at the top is greater than at the base of the flare, and the
    overhang increases monotonically up the flare.'''
    base_r, wall_h, flare_h, top_r = 5.0, 2.4, 1.4, 10.0
    steps = overhang_challenge(base_radius=base_r, wall_height=wall_h, flare_height=flare_h,
                               flare_radius=top_r, segments_per_layer=60)
    pts = _points(steps)
    zmax = max(p.z for p in pts)

    # isolate the flare (top flare_h of the build) and bin it by height
    flare = sorted((p for p in pts if p.z > zmax - flare_h - 1e-6), key=lambda p: p.z)
    n_bins = 6
    edges = [flare[0].z + (flare[-1].z - flare[0].z) * k / n_bins for k in range(n_bins + 1)]
    band_radii = []
    for lo, hi in zip(edges, edges[1:]):
        band = [_radius(p) for p in flare if lo <= p.z <= hi + 1e-9]
        if band:
            band_radii.append(sum(band) / len(band))

    assert band_radii[-1] > band_radii[0] + 2.0               # top clearly wider than the flare base
    assert band_radii[0] < base_r + 1.0                       # flare starts ~at the wall radius
    assert band_radii[-1] > top_r - 1.0                       # ...and reaches ~the target top radius
    # monotonically increasing overhang up the flare
    assert all(b > a for a, b in zip(band_radii, band_radii[1:]))


def test_plus_changes_the_cross_section_to_a_polygon():
    'The base challenge wall is a circle (constant radius); the Plus wall is a polygon (varying).'
    common = dict(wall_height=2.4, flare_height=1.4, segments_per_layer=120, sides=6)
    base_wall = [_radius(p) for p in _points(overhang_challenge(**common)) if 1.0 < p.z < 2.0]
    plus_wall = [_radius(p) for p in _points(overhang_challenge(plus=True, **common))
                 if 1.0 < p.z < 2.0]

    assert max(base_wall) - min(base_wall) < 0.05            # circle: radius is constant
    assert max(plus_wall) - min(plus_wall) > 0.3            # hexagon: vertex radius > edge midpoint


def test_plus_hexagon_has_the_right_number_of_corners():
    'A `sides`-gon wall has exactly `sides` radius maxima (corners) around one turn.'
    sides, n = 6, 240
    steps = overhang_challenge(plus=True, sides=sides, wall_height=2.4, flare_height=1.4,
                               segments_per_layer=n)
    wall = [p for p in _points(steps) if 1.0 < p.z < 1.0 + 0.5][:n]      # one turn of the wall
    rs = [_radius(p) for p in wall]
    # strict cyclic local maxima (a vertex can land on the slice boundary, so wrap around)
    corners = sum(1 for i in range(len(rs))
                  if rs[i] > rs[i - 1] and rs[i] > rs[(i + 1) % len(rs)])
    assert corners == sides


def test_plus_inward_option_leans_the_wall_inward_instead_of_outward():
    'Plus exposes inward vs outward lean: outward grows the radius, inward shrinks it.'
    common = dict(plus=True, base_radius=5.0, flare_radius=10.0, segments_per_layer=60)
    out = _points(overhang_challenge(outward=True, **common))
    inn = _points(overhang_challenge(outward=False, **common))

    def top_radius(pts):
        zmax = max(p.z for p in pts)
        top = [_radius(p) for p in pts if p.z > zmax - 0.1]
        return sum(top) / len(top)

    assert top_radius(out) > 5.0 + 2.0                       # outward: clearly wider than the wall
    assert top_radius(inn) < 5.0 - 2.0                       # inward: clearly narrower than the wall
