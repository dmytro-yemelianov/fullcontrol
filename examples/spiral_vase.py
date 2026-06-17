"""A smooth single-wall spiral (vase-mode) cylinder - the canonical FullControl 'hello world'.

The nozzle traces one continuous helix: the radius is constant and z rises a little every step, so
there are no layer changes and no seam. This is the simplest design that shows off non-layered,
continuously-varying toolpaths, and is the base that ripple_vase / wave_bowl build on.
"""
from math import tau, sin

import fullcontrol as fc


def spiral_vase(radius: float = 15.0, height: float = 30.0, layer_height: float = 0.24,
                segments_per_layer: int = 128, lobes: int = 0, lobe_depth: float = 2.0,
                extrusion_width: float = 0.6, centre=(50.0, 50.0),
                first_layer_gap: float = 0.8) -> list:
    """Build a vase-mode spiral.

    radius: nominal wall radius (mm).
    height: total height (mm).
    layer_height: z rise per full turn (mm) - the effective layer height.
    segments_per_layer: polyline resolution per turn (higher = smoother).
    lobes: number of radial lobes (0 = a plain cylinder; 3-8 makes a fluted vase).
    lobe_depth: how far each lobe pushes the wall in/out (mm).
    extrusion_width / first_layer_gap / centre: print setup.
    """
    cx, cy = centre
    eh = layer_height
    turns = height / eh
    total_segments = max(1, int(turns * segments_per_layer))
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac = i / segments_per_layer          # turns completed so far
        angle = frac * tau
        z = frac * eh + first_layer_gap
        r = radius + (lobe_depth * sin(lobes * angle) if lobes else 0.0)
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z), r, angle))
    return steps


if __name__ == '__main__':
    steps = spiral_vase()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='spiral_vase',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote spiral_vase.gcode')
