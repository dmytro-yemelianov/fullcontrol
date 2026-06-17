"""Twisted polygon vase - a vase-mode spiral whose cross-section is a regular polygon that rotates
as it rises, and optionally morphs from one vertex count to another up the height.

The cross-section radius follows the polygon outline: for a regular n-gon the distance from the
centre to the edge at perimeter angle phi is apothem / cos(phi folded into one sector). Adding a
height-proportional rotation to phi twists the polygon; linearly blending two polygon radii morphs
the shape (e.g. triangle at the base -> hexagon at the rim). One continuous seam-free toolpath.
"""
from math import tau, pi, cos

import fullcontrol as fc


def _ngon_radius(angle: float, sides: int, circumradius: float) -> float:
    'Distance from centre to a regular polygon edge at `angle` (a vertex sits at angle 0).'
    sector = tau / sides
    apothem = circumradius * cos(pi / sides)
    return apothem / cos((angle % sector) - sector / 2)


def twisted_polygon_vase(sides: int = 5, radius: float = 20.0, height: float = 40.0,
                         twist_turns: float = 0.5, morph_to_sides: int = 0,
                         layer_height: float = 0.24, segments_per_layer: int = 128,
                         extrusion_width: float = 0.6, centre=(50.0, 50.0),
                         first_layer_gap: float = 0.8) -> list:
    """Build a twisted (optionally morphing) polygon vase.

    sides: vertices of the base cross-section polygon.
    twist_turns: full polygon rotations over the whole height (0.5 = half turn; negative reverses).
    morph_to_sides: if > 0, the cross-section blends from `sides` at the base to this at the rim.
    radius: circumradius (centre-to-vertex) of the polygon (mm).
    """
    cx, cy = centre
    eh = layer_height
    turns = height / eh
    total_segments = max(1, int(turns * segments_per_layer))
    end_sides = morph_to_sides if morph_to_sides > 0 else sides
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh
        f = min(1.0, h / height)                          # 0 at base, 1 at rim
        twist = f * twist_turns * tau                     # rotate the polygon with height
        r_a = _ngon_radius(angle - twist, sides, radius)
        r = r_a if end_sides == sides else (1 - f) * r_a + f * _ngon_radius(angle - twist, end_sides, radius)
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = twisted_polygon_vase(sides=5, twist_turns=0.75, morph_to_sides=8)
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='twisted_polygon_vase',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote twisted_polygon_vase.gcode')
