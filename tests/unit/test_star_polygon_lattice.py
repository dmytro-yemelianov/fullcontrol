"""The Star-Polygon Lattice gallery design must resolve cleanly through all four backends and carry
the mathematical {n/k} star-polygon structure of the real FullControl research model.

These mirror tests/unit/test_examples.py: a small lattice is generated and run to gcode, simulation
and validation (non-trivial toolpath, material deposited, in-bounds, no errors), plus geometry
asserts that prove the star-polygon structure - n outer vertices per cell and the characteristic
self-crossing step-k connectivity (the vertex sequence skips k each hop).
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.star_polygon_lattice import star_polygon_lattice, _star_polygon, is_valid_star

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small():
    # a {5/2} pentagram lattice, kept small so the suite stays fast
    return star_polygon_lattice(points=5, step=2, radius=4, cols=4, rows=2, layers=1)


def test_design_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


def test_design_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


def test_design_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_design_starts_with_its_own_extrusion_geometry():
    'Self-contained: the step list opens with the ExtrusionGeometry from the catalogue (0.5 x 0.2).'
    steps = star_polygon_lattice()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.5 and steps[0].height == 0.2


def test_single_star_has_n_outer_vertices():
    'A {n/k} star places n points on a circle: count the distinct outer (radial-maximum) vertices.'
    for n, k in [(5, 2), (7, 3), (8, 3)]:
        loop = _star_polygon(0.0, 0.0, 0.0, 5.0, n, k, math.tau / 4)
        angles = {round(math.atan2(p.y, p.x), 4) for p in loop}
        assert len(angles) == n                      # exactly n outer vertices
        # every vertex sits on the circumradius (it is a regular star polygon)
        for p in loop:
            assert abs(math.hypot(p.x, p.y) - 5.0) < 1e-9


def test_star_polygon_step_k_connectivity():
    'The pen skips exactly k vertices each hop - the defining self-crossing {n/k} connectivity.'
    n, k, radius = 7, 3, 6.0
    loop = _star_polygon(0.0, 0.0, 0.0, radius, n, k, math.tau / 4)
    ideal = [(radius * math.cos(math.tau / 4 + i * math.tau / n),
              radius * math.sin(math.tau / 4 + i * math.tau / n)) for i in range(n)]
    seq = [min(range(n), key=lambda i: (p.x - ideal[i][0]) ** 2 + (p.y - ideal[i][1]) ** 2)
           for p in loop]
    assert seq[0] == seq[-1]                          # a single closed stroke (returns to start)
    diffs = [(seq[i + 1] - seq[i]) % n for i in range(len(seq) - 1)]
    assert all(d == k for d in diffs)                 # every hop skips exactly k
    assert sorted(set(seq)) == list(range(n))         # ...and visits every vertex once


def test_outer_vertex_count_equals_points_param():
    'The number of outer vertices in each lattice cell equals the `points` parameter.'
    points, step, radius = 5, 2, 4.0
    steps = star_polygon_lattice(points=points, step=step, radius=radius,
                                 cols=1, rows=1, layers=1)
    pts = [s for s in steps if isinstance(s, Point)]
    cx = 30 + radius
    cy = 30 + radius
    angles = {round(math.atan2(p.y - cy, p.x - cx), 3) for p in pts}
    assert len(angles) == points                      # outer-vertex count == points


def test_lattice_tiles_into_a_grid_as_one_continuous_bead():
    'A cols x rows grid of stars, all in one bead (no plain-cylinder collapse), flat and in layers.'
    cols, rows, radius = 4, 3, 4.0
    steps = star_polygon_lattice(points=5, step=2, radius=radius, cols=cols, rows=rows, layers=2)
    pts = [s for s in steps if isinstance(s, Point)]
    per_star = 5 + 1                                  # n hops + close
    assert len(pts) == per_star * cols * rows * 2     # every cell drawn, in both layers

    # the grid spreads across cols in x and rows in y (a tiled lattice, not a single star)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    assert max(xs) - min(xs) > radius * 2 * (cols - 1)
    assert max(ys) - min(ys) > radius * 2 * (rows - 1)

    # flat planar wall: each layer is a single z, layers step up by the extrusion height
    zlevels = sorted({round(p.z, 4) for p in pts})
    assert len(zlevels) == 2
    assert abs((zlevels[1] - zlevels[0]) - 0.2) < 1e-9


def test_default_proportions_match_the_published_flat_model():
    'The real Star-Polygon Lattice is flat (~0.2 mm tall, 2 layers) and a wide thin sheet.'
    steps = star_polygon_lattice()
    pts = [s for s in steps if isinstance(s, Point)]
    zs = [p.z for p in pts]
    assert max(zs) - min(zs) < 0.5                   # essentially flat (one z-change, like the gcode)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    assert (max(xs) - min(xs)) > (max(ys) - min(ys)) # a wide strip, like the ~68 x 30 published bbox


def test_is_valid_star_classifies_n_k():
    'Helper distinguishes true self-crossing stars from degenerate / convex cases.'
    assert is_valid_star(5, 2) and is_valid_star(7, 3) and is_valid_star(8, 3)
    assert not is_valid_star(6, 2)                   # gcd(6,2)=2 -> two triangles, not one stroke
    assert not is_valid_star(5, 1)                   # k=1 -> plain convex pentagon
    assert not is_valid_star(4, 2)                   # n/k too small to form a star


def test_step_one_is_a_convex_polygon():
    'k = 1 degenerates to a plain convex {n}-gon (consecutive vertices, no self-crossing).'
    n, radius = 6, 4.0
    loop = _star_polygon(0.0, 0.0, 0.0, radius, n, 1, math.tau / 4)
    ideal = [(radius * math.cos(math.tau / 4 + i * math.tau / n),
              radius * math.sin(math.tau / 4 + i * math.tau / n)) for i in range(n)]
    seq = [min(range(n), key=lambda i: (p.x - ideal[i][0]) ** 2 + (p.y - ideal[i][1]) ** 2)
           for p in loop]
    diffs = [(seq[i + 1] - seq[i]) % n for i in range(len(seq) - 1)]
    assert all(d == 1 for d in diffs)                # consecutive vertices -> convex hexagon
