"""Pin-Support Challenge - a tall slender vertical pin grown as one continuous Z-direction bead,
then capped with a wide cone, all support-free (that's the challenge).

The real FullControl model (fullcontrol.xyz "Pin-Support Challenge") prints in three continuous
phases on a single seam-free toolpath:

  1. a flat spiral disc on the bed that anchors the print and spirals inward to the centre
     (or, with ``conical_start=True``, a small tapered cone instead of a flat disc),
  2. a thin vertical PIN - the nozzle climbs straight up in place, extruding a single narrow
     pillar (the support-free feature being tested), then
  3. a wide CONE spiralled on top, opening out from the pin tip - the "print a sphere or cone on
     top" payload that the slender pin has to hold up unsupported.

Reverse-engineered from pin-support-challenge.gcode: bbox ~19.7 x 19.8 x 30 mm, centred at (50,50);
a ~4.8 mm-radius flat spiral base at z=0.2, a 20 mm vertical pin at the centre (r=0), then a 45-deg
cone (dr/dz = 1.0 exactly) opening from r=0 to r~10 mm over the top 10 mm, spiralled at ~0.26 mm per
turn. This reimplementation keeps that geometry parametric: a tall narrow pin topped by a wider cone,
faithful to the real ~20 mm footprint and 30 mm height.
"""
from math import tau

import fullcontrol as fc


def pin_support_challenge(pillar_diameter: float = 1.2, height: float = 20.0,
                          cone_radius: float = 10.0, base_radius: float = 5.0,
                          conical_start: bool = False, nozzle_size: float = 0.4,
                          layer_height: float = 0.24, segments_per_layer: int = 64,
                          centre=(50.0, 50.0), first_layer_gap: float = 0.0) -> list:
    """Build a Pin-Support Challenge: flat/conical base -> tall thin pin -> wide cone on top.

    pillar_diameter: width of the vertical pin (mm) - the slender support-free feature.
    height: height of the vertical pin (mm) before the cone starts.
    cone_radius: radius the cone opens out to at the very top (mm); its height equals cone_radius
        (a 45-degree cone, matching the real model's dr/dz = 1.0).
    base_radius: radius of the anchoring base printed on the bed (mm).
    conical_start: False = a flat spiral disc base; True = a short tapered cone base instead.
    nozzle_size: nozzle diameter (mm); sets the extrusion width.
    layer_height: z rise per full turn of the spiralled sections (mm).
    segments_per_layer: polyline resolution per turn (higher = smoother).
    centre / first_layer_gap: print placement.

    Returns a list of FullControl steps starting with its own ExtrusionGeometry.
    """
    cx, cy = centre
    eh = layer_height
    z0 = first_layer_gap + eh                       # top of the first deposited layer
    steps = [fc.ExtrusionGeometry(width=nozzle_size, height=eh)]

    # --- 1. base: a spiral anchoring the pin to the bed (flat disc, or a short tapered cone) ---
    base_height = base_radius if conical_start else 0.0     # conical base rises; flat base does not
    base_turns = max(1.0, base_radius / max(nozzle_size, 1e-6))   # pack rings ~one bead apart
    base_segments = max(1, int(base_turns * segments_per_layer))
    for i in range(base_segments + 1):
        frac = 1.0 - i / base_segments              # spiral inward: r goes base_radius -> 0
        angle = (i / segments_per_layer) * tau
        r = base_radius * frac
        z = z0 + base_height * (1.0 - frac)         # flat (base_height=0) or rising to the apex
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z), r, angle))

    pin_base_z = z0 + base_height                   # the pin starts at the centre of the base apex

    # --- 2. the pin: a single thin vertical bead climbing straight up in place ---
    pin_top_z = pin_base_z + height
    steps.append(fc.Point(x=cx, y=cy, z=pin_base_z))
    steps.append(fc.Point(x=cx, y=cy, z=pin_top_z))

    # --- 3. the cone on top: spiral out from the pin tip (45-degree: cone height == cone_radius) ---
    cone_turns = max(1.0, cone_radius / eh)
    cone_segments = max(1, int(cone_turns * segments_per_layer))
    for i in range(cone_segments + 1):
        frac = i / cone_segments                    # 0 at the tip, 1 at the rim
        angle = (i / segments_per_layer) * tau
        r = cone_radius * frac
        z = pin_top_z + cone_radius * frac          # dr/dz = 1.0 -> 45-degree cone
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z), r, angle))

    return steps


if __name__ == '__main__':
    steps = pin_support_challenge()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='pin_support_challenge',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.4, 'extrusion_height': 0.24}))
    print('wrote pin_support_challenge.gcode')
