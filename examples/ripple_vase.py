"""Ripple-texture star vase - a reimplementation of models/ripple_texture.ipynb.

Vase-mode spiral whose radius is modulated by three superimposed effects, all driven by the single
running parameter `frac` (turns completed):
  - ripples: a fast in/out radial wave the nozzle performs many times per layer (the surface texture),
  - star tips: a slow lobed modulation that makes the cross-section a pointed star,
  - bulge: a height-dependent swell so the vase is fattest in the middle.
The half-extra ripple per layer offsets the texture on alternating layers, giving the woven look.
"""
from math import tau, cos, sin

import fullcontrol as fc


def ripple_vase(height: float = 30.0, inner_radius: float = 15.0, ripples_per_layer: int = 50,
                ripple_depth: float = 1.0, star_tips: int = 4, tip_length: float = 5.0,
                tip_pointiness: float = 1.5, bulge: float = 2.0, twist_percent: float = 10.0,
                layer_height: float = 0.24, ripple_segments: int = 2,
                extrusion_width: float = 1.0, centre=(50.0, 50.0),
                first_layer_gap: float = 0.8) -> list:
    """See module docstring for the geometry. Defaults make a ~30 mm 4-point star ripple vase.

    ripple_segments: nodes per ripple (2 = zig-zag; raise for smoother waves at more points).
    twist_percent: full-rotation twist over the height (100 = one extra turn, negative = clockwise).
    """
    cx, cy = centre
    eh = layer_height
    layers = max(1, int(height / eh))
    segs_per_layer = (ripples_per_layer + 0.5) * ripple_segments
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for t in range(int(layers * segs_per_layer) + 1):
        frac = t / segs_per_layer                      # 0 .. layers
        angle = frac * tau * (1 + (twist_percent / 100) / layers) - tau / 4
        z = frac * eh
        ripple = ripple_depth * (0.5 + 0.5 * cos((ripples_per_layer + 0.5) * frac * tau))
        star = tip_length * (0.5 - 0.5 * cos(star_tips * frac * tau)) ** tip_pointiness if star_tips else 0.0
        swell = bulge * sin((z / height) * 0.5 * tau)
        r = inner_radius + ripple + star + swell
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = ripple_vase()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='ripple_vase',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 1.0, 'extrusion_height': 0.24}))
    print('wrote ripple_vase.gcode')
