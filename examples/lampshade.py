"""A mathematically defined parametric lampshade - a tall, flaring, single-wall vase-mode shade.

A FullControl Lampshade is a thin-wall surface of revolution printed in one continuous seam-free
spiral (vase mode), carrying vertical ribs/facets cut into its wall. The wall flares from an inner
"hole" radius at the base out to a wider rim, and the ribs run up the height as an "inner frame":
where they bite inward they thin the wall, so printed in a translucent material the ribs cast bright
and dark light patterns through the shade. One support-free toolpath.

The shade radius at height fraction f and angle is:

    r(f, angle) = internal_hole_radius                      # the base hole
                + inner_frame_amplitude * f                 # linear flare with height (the frame)
                + rib_depth * (cos(ribs * (angle + twist)) - 1) / 2   # ribs cut inward (<= 0)

so the ribs only ever remove material (the crest sits on the smooth flare, troughs cut in by
rib_depth), keeping the silhouette a clean flaring cone with `ribs` flutes around it.
"""
from math import tau, cos

import fullcontrol as fc


def lampshade(internal_hole_radius: float = 15.0, inner_frame_amplitude: float = 17.5,
              centre_xy: float = 105.0, ribs: int = 12, rib_depth: float = 4.0,
              twist_turns: float = 0.0, height: float = 60.0, layer_height: float = 0.24,
              segments_per_layer: int = 160, extrusion_width: float = 0.6,
              first_layer_gap: float = 0.8) -> list:
    """Build a mathematically defined parametric lampshade (vase-mode, single wall, ribbed flare).

    internal_hole_radius: radius (mm) of the shade at its base - the central "hole" (catalogue param).
    inner_frame_amplitude: how far the wall flares outward from base to rim (mm) - the inner frame
        that the ribs ride on (catalogue param). Rim radius = internal_hole_radius + this.
    centre_xy: X and Y of the part centre (mm) - the shade is centred at (centre_xy, centre_xy)
        (catalogue param "Centre XY").
    ribs: number of vertical ribs/flutes cut into the wall (the facets that cast light patterns).
    rib_depth: how far each rib bites inward from the smooth flare (mm).
    twist_turns: full rib rotations over the whole height (0 = straight ribs; negative reverses).
    height: total height of the shade (mm).
    layer_height: z rise per full turn (mm) - the effective layer height.
    segments_per_layer: polyline resolution per turn (higher = smoother / sharper ribs).
    extrusion_width / first_layer_gap: print setup.
    """
    cx = cy = centre_xy
    eh = layer_height
    total_segments = max(1, int((height / eh) * segments_per_layer))
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh
        f = min(1.0, h / height)                                  # 0 at base, 1 at rim
        twist = f * twist_turns * tau                            # rotate the ribs with height
        flare = internal_hole_radius + inner_frame_amplitude * f  # smooth flaring cone
        # ribs only cut inward: (cos - 1)/2 is in [-1, 0], crest on the flare, trough -rib_depth
        rib = rib_depth * (cos(ribs * (angle + twist)) - 1.0) / 2.0
        r = flare + rib
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = lampshade()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='lampshade',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote lampshade.gcode')
