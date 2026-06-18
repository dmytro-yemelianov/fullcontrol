"""FullControl 'Overhang Challenge' (and its 'Plus' variant) - a vase-mode overhang test.

A reimplementation of the fullcontrol.xyz models "Overhang Challenge" (hash b70938, "Try to print
an overhang of 90 degrees") and "Overhang Challenge Plus" (hash 2d37a5, "...with different shapes and
either inwards or outwards from the supporting wall").

The real g-codes are a single continuous bead in three phases printed as one seamless spiral:

  1. a spiral-filled SOLID BASE DISC (radius `base_radius` out to `foot_radius`) so the object has a
     ~20 mm flat footprint to anchor it to the bed,
  2. a straight VERTICAL WALL at `base_radius` (a circle for the base challenge; a regular polygon for
     the Plus variant), then
  3. an OUTWARD FLARE near the top where the radius grows linearly with height (5 mm -> ~10 mm over
     ~1.4 mm of z in the originals): the wall leans progressively off vertical until it is an almost-
     90-degree overhang - the whole point of the test.

Reverse-engineered from the supplied g-codes:
  - overhang-challenge.gcode:      ~2176 pts, bbox 19.8 x 19.8 x 4.3 mm, circular wall (r=5),
    flare r 5->10 over z~3.1->4.5 (dr/dz ~ 3.76 -> ~75 deg off vertical, i.e. a steep overhang).
  - overhang-challenge-plus.gcode: ~186 pts,  bbox 17.1 x 19.7 x 4.3 mm, HEXAGONAL wall (circumradius
    5, vertices at +-30/+-90/+-150 deg), same outward flare.

Faithful: the three-phase spiral structure, the ~20 mm footprint and ~4.3 mm height, the linear
outward flare creating the steep overhang, the circle-vs-polygon cross-section of the Plus variant,
and the Plus inward/outward lean option. Approximated: exact segment counts / spiral fill spacing are
parametric here rather than copied verbatim; the originals' "Five-Stack (Heatsink Demo)" checkbox and
their XY/Z scale-factor sliders are folded into the `stack`, `scale_xy` and `scale_z` parameters.
"""
from math import tau, pi, cos

import fullcontrol as fc


def _ngon_radius(angle: float, sides: int, circumradius: float) -> float:
    'Distance from centre to a regular polygon edge at `angle` (a vertex sits at angle 0).'
    sector = tau / sides
    apothem = circumradius * cos(pi / sides)
    return apothem / cos((angle % sector) - sector / 2)


def overhang_challenge(base_radius: float = 5.0, foot_radius: float = 10.0,
                       wall_height: float = 2.4, flare_height: float = 1.4,
                       flare_radius: float = 10.0, plus: bool = False, sides: int = 6,
                       outward: bool = True, stack: int = 1, scale_xy: float = 1.0,
                       scale_z: float = 1.0, layer_height: float = 0.5,
                       segments_per_layer: int = 100, base_rings: int = 7,
                       extrusion_width: float = 0.6, centre=(50.0, 50.0),
                       first_layer_gap: float = 0.0) -> list:
    """Build an Overhang Challenge: a spiral-filled foot, a straight wall, then an outward flare.

    base_radius: radius of the vertical wall / circumradius of the Plus polygon (mm).
    foot_radius: outer radius of the spiral-filled solid base disc (the ~20 mm footprint, mm).
    wall_height: height of the straight (vertical) wall section (mm).
    flare_height: height over which the wall flares outward - the overhang test region (mm).
    flare_radius: radius reached at the very top of the flare (mm); > base_radius leans OUTWARD.
    plus: False = the base 'Overhang Challenge' (circular wall); True = 'Overhang Challenge Plus'
        (a regular `sides`-gon wall, and the lean direction is controllable via `outward`).
    sides: polygon vertex count for the Plus variant (ignored when plus is False).
    outward: Plus-only. True = wall flares outward (overhang); False = it tapers inward.
    stack: number of stacked copies printed on top of each other (the "Five-Stack / Heatsink Demo").
    scale_xy / scale_z: uniform scale factors mirroring the originals' Scale Factor XY / Z sliders.
    layer_height: z rise per spiral turn. base_rings: spiral rings in the solid base disc.
    """
    cx, cy = centre
    eh = layer_height * scale_z
    sxy = scale_xy
    n = max(8, segments_per_layer)
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]

    def cross_section_radius(r: float, angle: float) -> float:
        'Map a target circumradius to the wall cross-section (circle, or Plus polygon).'
        if plus:
            return _ngon_radius(angle, max(3, sides), r)
        return r

    # for the Plus variant, "outward" toggles whether the flare grows or shrinks the wall
    top_radius = flare_radius if (not plus or outward) else max(0.5, 2 * base_radius - flare_radius)

    z = first_layer_gap
    for _ in range(max(1, stack)):
        z0 = z

        # phase 1: spiral-filled solid base disc (anchors the ~20 mm footprint to the bed)
        rings = max(1, base_rings)
        ring_steps = rings * n
        for i in range(ring_steps + 1):
            frac = i / ring_steps
            angle = frac * rings * tau
            r = (base_radius + (foot_radius - base_radius) * frac) * sxy
            steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z0), r, angle))

        # phase 2: straight vertical wall (circle, or Plus polygon), as a continuous spiral
        wall_turns = max(1, round(wall_height / eh))
        for i in range(1, wall_turns * n + 1):
            frac = i / n
            angle = frac * tau
            r = cross_section_radius(base_radius, angle) * sxy
            steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z0 + frac * eh), r, angle))
        z_wall_top = z0 + wall_turns * eh

        # phase 3: the overhang - radius grows (or shrinks) linearly with height up the flare
        flare_turns = max(1, round(flare_height / eh))
        for i in range(1, flare_turns * n + 1):
            frac = i / n
            angle = frac * tau
            f = frac / flare_turns                       # 0 at wall top, 1 at the very top
            target = base_radius + (top_radius - base_radius) * f
            r = cross_section_radius(target, angle) * sxy
            steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z_wall_top + frac * eh), r, angle))
        z = z_wall_top + flare_turns * eh

    return steps


if __name__ == '__main__':
    steps = overhang_challenge()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='overhang_challenge',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.5}))
    print('wrote overhang_challenge.gcode')
