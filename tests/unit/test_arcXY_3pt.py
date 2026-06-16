"""HIGH-2: arcXY_3pt must produce an arc that actually passes through the middle point.

The angle-normalisation loop was a no-op (it mutated only the loop variable), so the
direction/sweep was computed from raw atan2 output and produced the wrong arc whenever
the three points straddled the +/-pi boundary.
"""
from math import radians, cos, sin

import fullcontrol as fc


def _pt_on_circle(centre, radius, angle_deg):
    a = radians(angle_deg)
    return fc.Point(x=centre.x + radius * cos(a), y=centre.y + radius * sin(a), z=0)


def _min_distance_to_arc(arc, pt):
    return min(((p.x - pt.x) ** 2 + (p.y - pt.y) ** 2) ** 0.5 for p in arc)


def test_arc_passes_through_mid_point_across_pi_boundary():
    # angles 170 / 181 / 190 deg: pt2 sits just past +180deg where atan2 wraps to -pi
    centre, radius = fc.Point(x=0, y=0, z=0), 1.0
    pt1 = _pt_on_circle(centre, radius, 170)
    pt2 = _pt_on_circle(centre, radius, 181)
    pt3 = _pt_on_circle(centre, radius, 190)

    arc = fc.arcXY_3pt(pt1, pt2, pt3, segments=200)

    # the short arc 170->181->190 must visit pt2; the buggy long-way arc misses it badly
    assert _min_distance_to_arc(arc, pt2) < 0.02


def test_arc_endpoints_and_radius_are_consistent():
    centre, radius = fc.Point(x=2, y=-3, z=0), 5.0
    pt1 = _pt_on_circle(centre, radius, 10)
    pt2 = _pt_on_circle(centre, radius, 80)
    pt3 = _pt_on_circle(centre, radius, 150)

    arc = fc.arcXY_3pt(pt1, pt2, pt3, segments=120)

    assert _min_distance_to_arc(arc, pt1) < 1e-6
    assert _min_distance_to_arc(arc, pt2) < 0.02
    assert _min_distance_to_arc(arc, pt3) < 1e-6
    for p in arc:
        r = ((p.x - centre.x) ** 2 + (p.y - centre.y) ** 2) ** 0.5
        assert abs(r - radius) < 1e-6
