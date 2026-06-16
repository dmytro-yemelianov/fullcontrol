"""Characterization unit tests for fullcontrol.geometry.

These tests assert geometric invariants and known values (not blind snapshots)
so future refactors of the geometry module are safe. Every test passes against
the current code. Where a test would have to assert a value that looks like a
genuine bug, it is skipped with an explanation rather than locking in the bug.
"""

from math import cos, pi, radians, sin

import pytest

import fullcontrol as fc
from fullcontrol.geometry.measure import distance_forgiving
from fullcontrol.geometry.midpoint import interpolated_point, midpoint
from fullcontrol.geometry.waves import sinewaveXYpolar

EXACT = 1e-6  # tolerance for exact mathematical identities
LOOSE = 1e-3  # tolerance for segment-resolution / discretised checks


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _radius(point, centre):
    return ((point.x - centre.x) ** 2 + (point.y - centre.y) ** 2) ** 0.5


def _point_on_circle(centre, radius, angle_deg):
    a = radians(angle_deg)
    return fc.Point(x=centre.x + radius * cos(a), y=centre.y + radius * sin(a), z=centre.z)


def _min_dist_to_path(path, pt):
    return min(((p.x - pt.x) ** 2 + (p.y - pt.y) ** 2) ** 0.5 for p in path)


# ---------------------------------------------------------------------------
# circleXY
# ---------------------------------------------------------------------------

def test_circleXY_returns_segments_plus_one_points():
    circle = fc.circleXY(fc.Point(x=0, y=0, z=0), 5.0, 0.0, segments=24)
    assert len(circle) == 25


def test_circleXY_every_point_at_radius_from_centre():
    centre = fc.Point(x=3, y=-2, z=7)
    circle = fc.circleXY(centre, 4.0, 0.7, segments=40)
    for p in circle:
        assert abs(_radius(p, centre) - 4.0) < EXACT


def test_circleXY_z_matches_centre():
    centre = fc.Point(x=0, y=0, z=12.5)
    circle = fc.circleXY(centre, 2.0, 0.0, segments=10)
    for p in circle:
        assert abs(p.z - 12.5) < EXACT


def test_circleXY_is_closed_loop():
    centre = fc.Point(x=1, y=1, z=0)
    circle = fc.circleXY(centre, 3.0, 0.3, segments=30)
    assert abs(circle[0].x - circle[-1].x) < EXACT
    assert abs(circle[0].y - circle[-1].y) < EXACT


def test_circleXY_starts_at_start_angle():
    centre = fc.Point(x=0, y=0, z=0)
    radius, start = 2.0, radians(30)
    circle = fc.circleXY(centre, radius, start, segments=12)
    assert abs(circle[0].x - radius * cos(start)) < EXACT
    assert abs(circle[0].y - radius * sin(start)) < EXACT


# ---------------------------------------------------------------------------
# circleXY_3pt
# ---------------------------------------------------------------------------

def test_circleXY_3pt_points_on_circle_through_three_points():
    # three points on a known circle: centre (0,0), radius 5
    centre = fc.Point(x=0, y=0, z=0)
    pt1 = _point_on_circle(centre, 5.0, 0)
    pt2 = _point_on_circle(centre, 5.0, 120)
    pt3 = _point_on_circle(centre, 5.0, 240)
    circle = fc.circleXY_3pt(pt1, pt2, pt3, start_at_first_point=True, segments=36)
    assert len(circle) == 37
    for p in circle:
        assert abs(_radius(p, centre) - 5.0) < EXACT


def test_circleXY_3pt_start_at_first_point():
    centre = fc.Point(x=2, y=3, z=0)
    pt1 = _point_on_circle(centre, 4.0, 15)
    pt2 = _point_on_circle(centre, 4.0, 95)
    pt3 = _point_on_circle(centre, 4.0, 200)
    circle = fc.circleXY_3pt(pt1, pt2, pt3, start_at_first_point=True, segments=50)
    assert abs(circle[0].x - pt1.x) < EXACT
    assert abs(circle[0].y - pt1.y) < EXACT


def test_circleXY_3pt_requires_a_start_specifier():
    pt1 = fc.Point(x=1, y=0, z=0)
    pt2 = fc.Point(x=0, y=1, z=0)
    pt3 = fc.Point(x=-1, y=0, z=0)
    with pytest.raises(Exception):
        fc.circleXY_3pt(pt1, pt2, pt3, segments=10)


# ---------------------------------------------------------------------------
# arcXY
# ---------------------------------------------------------------------------

def test_arcXY_returns_segments_plus_one_points():
    arc = fc.arcXY(fc.Point(x=0, y=0, z=0), 3.0, 0.0, pi, segments=20)
    assert len(arc) == 21


def test_arcXY_start_and_end_positions():
    centre = fc.Point(x=0, y=0, z=0)
    radius, start, arc_angle = 2.0, radians(20), radians(100)
    arc = fc.arcXY(centre, radius, start, arc_angle, segments=50)
    assert abs(arc[0].x - radius * cos(start)) < EXACT
    assert abs(arc[0].y - radius * sin(start)) < EXACT
    end = start + arc_angle
    assert abs(arc[-1].x - radius * cos(end)) < EXACT
    assert abs(arc[-1].y - radius * sin(end)) < EXACT


def test_arcXY_radius_invariance():
    centre = fc.Point(x=-4, y=6, z=1)
    arc = fc.arcXY(centre, 7.0, radians(10), radians(200), segments=64)
    for p in arc:
        assert abs(_radius(p, centre) - 7.0) < EXACT


# ---------------------------------------------------------------------------
# arcXY_3pt  (recently bug-fixed: arc must pass through the mid point)
# ---------------------------------------------------------------------------

def test_arcXY_3pt_passes_through_all_three_points():
    centre = fc.Point(x=2, y=-3, z=0)
    pt1 = _point_on_circle(centre, 5.0, 10)
    pt2 = _point_on_circle(centre, 5.0, 80)
    pt3 = _point_on_circle(centre, 5.0, 150)
    arc = fc.arcXY_3pt(pt1, pt2, pt3, segments=200)
    assert _min_dist_to_path(arc, pt1) < EXACT
    assert _min_dist_to_path(arc, pt2) < LOOSE
    assert _min_dist_to_path(arc, pt3) < EXACT


def test_arcXY_3pt_mid_point_when_wrapping_past_pi():
    # angles 170 / 181 / 190 deg: pt2 sits just past +180deg where atan2 wraps to -pi
    centre = fc.Point(x=0, y=0, z=0)
    pt1 = _point_on_circle(centre, 1.0, 170)
    pt2 = _point_on_circle(centre, 1.0, 181)
    pt3 = _point_on_circle(centre, 1.0, 190)
    arc = fc.arcXY_3pt(pt1, pt2, pt3, segments=200)
    # the short arc 170->181->190 must visit pt2; the buggy long-way arc misses it badly
    assert _min_dist_to_path(arc, pt2) < 0.02


def test_arcXY_3pt_radius_invariance():
    centre = fc.Point(x=1, y=1, z=0)
    pt1 = _point_on_circle(centre, 3.5, 0)
    pt2 = _point_on_circle(centre, 3.5, 70)
    pt3 = _point_on_circle(centre, 3.5, 160)
    arc = fc.arcXY_3pt(pt1, pt2, pt3, segments=100)
    for p in arc:
        assert abs(_radius(p, centre) - 3.5) < EXACT


# ---------------------------------------------------------------------------
# ellipseXY / elliptical_arcXY
# ---------------------------------------------------------------------------

def test_ellipseXY_points_satisfy_ellipse_equation():
    centre = fc.Point(x=0, y=0, z=0)
    a, b = 4.0, 2.0
    ellipse = fc.ellipseXY(centre, a, b, 0.0, segments=60)
    for p in ellipse:
        lhs = ((p.x - centre.x) / a) ** 2 + ((p.y - centre.y) / b) ** 2
        assert abs(lhs - 1.0) < EXACT


def test_ellipseXY_returns_segments_plus_one_points_and_closed():
    ellipse = fc.ellipseXY(fc.Point(x=0, y=0, z=0), 3.0, 5.0, 0.0, segments=20)
    assert len(ellipse) == 21
    assert abs(ellipse[0].x - ellipse[-1].x) < EXACT
    assert abs(ellipse[0].y - ellipse[-1].y) < EXACT


def test_elliptical_arcXY_points_satisfy_ellipse_equation():
    from fullcontrol.geometry import elliptical_arcXY
    centre = fc.Point(x=2, y=-1, z=3)
    a, b = 6.0, 3.0
    arc = elliptical_arcXY(centre, a, b, radians(20), radians(120), segments=40)
    assert len(arc) == 41
    for p in arc:
        lhs = ((p.x - centre.x) / a) ** 2 + ((p.y - centre.y) / b) ** 2
        assert abs(lhs - 1.0) < EXACT
        assert abs(p.z - centre.z) < EXACT


# ---------------------------------------------------------------------------
# rectangleXY
# ---------------------------------------------------------------------------

def test_rectangleXY_returns_five_points():
    rect = fc.rectangleXY(fc.Point(x=0, y=0, z=0), 4.0, 3.0)
    assert len(rect) == 5


def test_rectangleXY_is_closed():
    start = fc.Point(x=1, y=2, z=0)
    rect = fc.rectangleXY(start, 4.0, 3.0)
    assert abs(rect[0].x - rect[-1].x) < EXACT
    assert abs(rect[0].y - rect[-1].y) < EXACT


def test_rectangleXY_dimensions():
    rect = fc.rectangleXY(fc.Point(x=0, y=0, z=0), 4.0, 3.0)
    xs = [p.x for p in rect]
    ys = [p.y for p in rect]
    assert abs((max(xs) - min(xs)) - 4.0) < EXACT
    assert abs((max(ys) - min(ys)) - 3.0) < EXACT


def test_rectangleXY_right_angle_corners():
    rect = fc.rectangleXY(fc.Point(x=0, y=0, z=0), 4.0, 3.0)
    # check the angle at each of the 4 distinct corners is 90 degrees
    for i in range(4):
        a = rect[i]
        b = rect[(i + 1) % 4]
        c = rect[(i + 2) % 4]
        v1 = (a.x - b.x, a.y - b.y)
        v2 = (c.x - b.x, c.y - b.y)
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        assert abs(dot) < EXACT  # perpendicular -> dot product zero


# ---------------------------------------------------------------------------
# polygonXY
# ---------------------------------------------------------------------------

def test_polygonXY_returns_n_plus_one_points():
    poly = fc.polygonXY(fc.Point(x=0, y=0, z=0), 5.0, 0.0, sides=6)
    assert len(poly) == 7


def test_polygonXY_vertices_on_circumscribing_circle():
    centre = fc.Point(x=2, y=2, z=0)
    enclosing_radius = 5.0
    poly = fc.polygonXY(centre, enclosing_radius, radians(10), sides=5)
    for p in poly:
        assert abs(_radius(p, centre) - enclosing_radius) < EXACT


def test_polygonXY_is_closed():
    poly = fc.polygonXY(fc.Point(x=0, y=0, z=0), 3.0, 0.0, sides=8)
    assert abs(poly[0].x - poly[-1].x) < EXACT
    assert abs(poly[0].y - poly[-1].y) < EXACT


# ---------------------------------------------------------------------------
# spiralXY / helixZ
# ---------------------------------------------------------------------------

def test_spiralXY_radius_progresses_start_to_end():
    centre = fc.Point(x=0, y=0, z=0)
    spiral = fc.spiralXY(centre, 1.0, 5.0, 0.0, n_turns=3, segments=120)
    assert abs(_radius(spiral[0], centre) - 1.0) < EXACT
    assert abs(_radius(spiral[-1], centre) - 5.0) < EXACT


def test_spiralXY_radius_monotonic_increasing():
    centre = fc.Point(x=0, y=0, z=0)
    spiral = fc.spiralXY(centre, 1.0, 5.0, 0.0, n_turns=3, segments=120)
    radii = [_radius(p, centre) for p in spiral]
    for r0, r1 in zip(radii, radii[1:]):
        assert r1 >= r0 - EXACT


def test_spiralXY_z_constant():
    centre = fc.Point(x=0, y=0, z=4.0)
    spiral = fc.spiralXY(centre, 1.0, 5.0, 0.0, n_turns=2, segments=60)
    for p in spiral:
        assert abs(p.z - 4.0) < EXACT


def test_helixZ_z_monotonic_and_total_rise():
    centre = fc.Point(x=0, y=0, z=0)
    n_turns, pitch_z = 4, 2.0
    helix = fc.helixZ(centre, 3.0, 3.0, 0.0, n_turns=n_turns, pitch_z=pitch_z, segments=160)
    zs = [p.z for p in helix]
    for z0, z1 in zip(zs, zs[1:]):
        assert z1 >= z0 - EXACT
    assert abs((zs[-1] - zs[0]) - pitch_z * n_turns) < EXACT


def test_helixZ_radius_constant_when_start_equals_end():
    centre = fc.Point(x=1, y=1, z=0)
    helix = fc.helixZ(centre, 3.0, 3.0, 0.0, n_turns=2, pitch_z=1.0, segments=80)
    for p in helix:
        assert abs(_radius(p, centre) - 3.0) < EXACT


# ---------------------------------------------------------------------------
# midpoint / interpolated_point
# ---------------------------------------------------------------------------

def test_midpoint_known_value():
    mp = midpoint(fc.Point(x=0, y=0, z=0), fc.Point(x=4, y=8, z=2))
    assert abs(mp.x - 2.0) < EXACT
    assert abs(mp.y - 4.0) < EXACT
    assert abs(mp.z - 1.0) < EXACT


def test_midpoint_none_coordinate_returns_none():
    mp = midpoint(fc.Point(x=0, y=None, z=0), fc.Point(x=10, y=5, z=10))
    assert abs(mp.x - 5.0) < EXACT
    assert mp.y is None
    assert abs(mp.z - 5.0) < EXACT


def test_interpolated_point_known_value():
    ip = interpolated_point(fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=20, z=30), 0.25)
    assert abs(ip.x - 2.5) < EXACT
    assert abs(ip.y - 5.0) < EXACT
    assert abs(ip.z - 7.5) < EXACT


def test_interpolated_point_endpoints():
    p1 = fc.Point(x=1, y=2, z=3)
    p2 = fc.Point(x=4, y=5, z=6)
    a = interpolated_point(p1, p2, 0.0)
    b = interpolated_point(p1, p2, 1.0)
    assert abs(a.x - p1.x) < EXACT and abs(a.y - p1.y) < EXACT and abs(a.z - p1.z) < EXACT
    assert abs(b.x - p2.x) < EXACT and abs(b.y - p2.y) < EXACT and abs(b.z - p2.z) < EXACT


def test_interpolated_point_none_coordinate_returns_none():
    ip = interpolated_point(fc.Point(x=0, y=None, z=0), fc.Point(x=10, y=5, z=10), 0.5)
    assert abs(ip.x - 5.0) < EXACT
    assert ip.y is None
    assert abs(ip.z - 5.0) < EXACT


# ---------------------------------------------------------------------------
# segmented_line / segmented_path
# ---------------------------------------------------------------------------

def test_segmented_line_returns_segments_plus_one_points():
    line = fc.segmented_line(fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0), 5)
    assert len(line) == 6


def test_segmented_line_endpoints_preserved():
    p1 = fc.Point(x=1, y=2, z=3)
    p2 = fc.Point(x=11, y=12, z=13)
    line = fc.segmented_line(p1, p2, 7)
    assert abs(line[0].x - p1.x) < EXACT and abs(line[0].y - p1.y) < EXACT and abs(line[0].z - p1.z) < EXACT
    assert abs(line[-1].x - p2.x) < EXACT and abs(line[-1].y - p2.y) < EXACT and abs(line[-1].z - p2.z) < EXACT


def test_segmented_line_even_spacing():
    line = fc.segmented_line(fc.Point(x=0, y=0, z=0), fc.Point(x=9, y=0, z=0), 9)
    gaps = [fc.distance(line[i], line[i + 1]) for i in range(len(line) - 1)]
    for g in gaps:
        assert abs(g - 1.0) < EXACT


def test_segmented_path_count_and_endpoints():
    pts = fc.segmented_line(fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0), 5)
    path = fc.segmented_path(pts, 4)
    assert len(path) == 5  # segments+1
    assert abs(path[0].x - 0.0) < EXACT
    assert abs(path[-1].x - 10.0) < EXACT


def test_segmented_path_even_spacing_on_straight_line():
    pts = fc.segmented_line(fc.Point(x=0, y=0, z=0), fc.Point(x=12, y=0, z=0), 6)
    path = fc.segmented_path(pts, 4)
    gaps = [fc.distance(path[i], path[i + 1]) for i in range(len(path) - 1)]
    for g in gaps:
        assert abs(g - 3.0) < LOOSE


# ---------------------------------------------------------------------------
# measure.py
# ---------------------------------------------------------------------------

def test_distance_345_triangle():
    d = fc.distance(fc.Point(x=0, y=0, z=0), fc.Point(x=3, y=4, z=0))
    assert abs(d - 5.0) < EXACT


def test_distance_3d():
    d = fc.distance(fc.Point(x=0, y=0, z=0), fc.Point(x=2, y=3, z=6))
    assert abs(d - 7.0) < EXACT  # sqrt(4+9+36)=7


def test_distance_forgiving_ignores_missing_axis():
    # z is None on both points -> treated as zero contribution -> 3-4-5
    d = distance_forgiving(fc.Point(x=0, y=0, z=None), fc.Point(x=3, y=4, z=None))
    assert abs(d - 5.0) < EXACT


def test_distance_forgiving_missing_on_one_point_only():
    # y missing on one point -> y contribution dropped, only x distance counts
    d = distance_forgiving(fc.Point(x=0, y=None, z=0), fc.Point(x=3, y=4, z=0))
    assert abs(d - 3.0) < EXACT


def test_angleXY_between_3_points_right_angle():
    # returns radians (the docstring says degrees, but the implementation returns
    # the raw polar-angle difference in radians)
    ang = fc.angleXY_between_3_points(
        fc.Point(x=1, y=0, z=0), fc.Point(x=0, y=0, z=0), fc.Point(x=0, y=1, z=0))
    assert abs(ang - pi / 2) < EXACT


def test_angleXY_between_3_points_straight_line():
    ang = fc.angleXY_between_3_points(
        fc.Point(x=1, y=0, z=0), fc.Point(x=0, y=0, z=0), fc.Point(x=-1, y=0, z=0))
    assert abs(ang - pi) < EXACT


def test_path_length_straight_line():
    pts = fc.segmented_line(fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0), 5)
    assert abs(fc.path_length(pts) - 10.0) < EXACT


# ---------------------------------------------------------------------------
# waves.py
# ---------------------------------------------------------------------------

def test_squarewaveXY_point_count():
    # squarewaveXYpolar emits start + 3 points per period + 1 join between periods
    periods = 3
    sq = fc.squarewaveXY(fc.Point(x=0, y=0, z=0), fc.Vector(x=1, y=0), 2.0, 1.0, periods)
    expected = 1 + 3 * periods + (periods - 1)
    assert len(sq) == expected


def test_squarewaveXY_amplitude_bounds():
    amplitude = 3.0
    sq = fc.squarewaveXY(fc.Point(x=0, y=0, z=0), fc.Vector(x=1, y=0), amplitude, 2.0, 2)
    ys = [p.y for p in sq]
    assert min(ys) > -EXACT
    assert abs(max(ys) - amplitude) < EXACT


def test_sinewaveXYpolar_point_count():
    periods, spp = 2, 16
    sw = sinewaveXYpolar(fc.Point(x=0, y=0, z=0), 0.0, 2.0, 10.0, periods, segments_per_period=spp)
    assert len(sw) == periods * spp + 1


def test_sinewaveXYpolar_amplitude_bounds():
    amplitude = 2.5
    sw = sinewaveXYpolar(fc.Point(x=0, y=0, z=0), 0.0, amplitude, 10.0, 3, segments_per_period=32)
    ys = [p.y for p in sw]
    # the wave is offset so y spans [0, amplitude]
    assert min(ys) > -EXACT
    assert max(ys) <= amplitude + EXACT
    assert abs(max(ys) - amplitude) < LOOSE


# ---------------------------------------------------------------------------
# linspace (fullcontrol.extra_functions)
# ---------------------------------------------------------------------------

def test_linspace_two_points_returns_start_and_end():
    result = fc.linspace(0.0, 10.0, 2)
    assert result == [0.0, 10.0]


def test_linspace_one_point_returns_start():
    assert fc.linspace(5.0, 99.0, 1) == [5.0]


def test_linspace_endpoints_exact():
    result = fc.linspace(-3.0, 7.0, 11)
    assert len(result) == 11
    assert abs(result[0] - (-3.0)) < EXACT
    assert abs(result[-1] - 7.0) < EXACT


def test_linspace_even_spacing():
    result = fc.linspace(0.0, 1.0, 5)
    gaps = [result[i + 1] - result[i] for i in range(len(result) - 1)]
    for g in gaps:
        assert abs(g - 0.25) < EXACT


# ---------------------------------------------------------------------------
# move / reflectXY
# ---------------------------------------------------------------------------

def test_move_single_point():
    moved = fc.move(fc.Point(x=1, y=2, z=3), fc.Vector(x=10, y=20, z=30))
    assert abs(moved.x - 11.0) < EXACT
    assert abs(moved.y - 22.0) < EXACT
    assert abs(moved.z - 33.0) < EXACT


def test_move_does_not_mutate_original():
    original = fc.Point(x=1, y=2, z=3)
    fc.move(original, fc.Vector(x=5, y=5, z=5))
    assert abs(original.x - 1.0) < EXACT
    assert abs(original.y - 2.0) < EXACT
    assert abs(original.z - 3.0) < EXACT


def test_move_copy_quantity():
    copies = fc.move(fc.Point(x=0, y=0, z=0), fc.Vector(x=2, y=0, z=0), copy=True, copy_quantity=4)
    assert len(copies) == 4
    xs = [p.x for p in copies]
    assert xs == [0.0, 2.0, 4.0, 6.0]


def test_reflectXY_about_x_axis():
    r = fc.reflectXY(fc.Point(x=2, y=3, z=5), fc.Point(x=0, y=0, z=0), fc.Point(x=1, y=0, z=0))
    assert abs(r.x - 2.0) < EXACT
    assert abs(r.y - (-3.0)) < EXACT
    assert abs(r.z - 5.0) < EXACT  # z preserved


def test_reflectXY_about_y_axis():
    r = fc.reflectXY(fc.Point(x=4, y=1, z=2), fc.Point(x=0, y=0, z=0), fc.Point(x=0, y=1, z=0))
    assert abs(r.x - (-4.0)) < EXACT
    assert abs(r.y - 1.0) < EXACT


def test_reflectXY_about_diagonal_swaps_xy():
    # reflection about line y=x maps (x,y) -> (y,x)
    r = fc.reflectXY(fc.Point(x=3, y=7, z=0), fc.Point(x=0, y=0, z=0), fc.Point(x=1, y=1, z=0))
    assert abs(r.x - 7.0) < EXACT
    assert abs(r.y - 3.0) < EXACT


def test_reflectXY_is_involution():
    # reflecting twice returns the original point
    p = fc.Point(x=5, y=-2, z=1)
    line_a = fc.Point(x=1, y=1, z=0)
    line_b = fc.Point(x=4, y=2, z=0)
    once = fc.reflectXY(p, line_a, line_b)
    twice = fc.reflectXY(once, line_a, line_b)
    assert abs(twice.x - p.x) < EXACT
    assert abs(twice.y - p.y) < EXACT
