"""Mobius band - a parametric non-planar ribbon with a single half-twist.

The classic Mobius surface: a loop of radius `loop_radius` whose ribbon cross-section rotates a half
turn (the `u/2` term) as it goes once around, so the band has one side and one edge. The toolpath
rasters the surface - a boustrophedon (zig-zag) across the ribbon `width` while marching around the
loop - producing one continuous bead over the whole twisted band.

This is an art piece: the ribbon floats and tilts, so unlike the vases it needs support to print -
but it's a striking parametric / visualisation design and one seamless toolpath.
"""
from math import tau, sin, cos

import fullcontrol as fc


def mobius_band(loop_radius: float = 20.0, width: float = 9.0, loop_segments: int = 360,
                strokes_across: int = 12, extrusion_width: float = 0.6, extrusion_height: float = 0.3,
                centre=(50.0, 50.0), base_gap: float = 0.8) -> list:
    """Build a Mobius band toolpath.

    loop_radius: radius of the band's centre-line loop (mm).
    width: ribbon width (mm).
    loop_segments: steps around the loop (resolution); strokes_across: zig-zag passes per position.
    The whole band is lifted so its lowest point clears the bed (it tilts up to +-width/2 in z).
    """
    cx, cy = centre
    base_z = width / 2 + base_gap          # lift so the deepest dip clears the bed
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=extrusion_height)]
    for iu in range(loop_segments + 1):
        u = iu / loop_segments * tau       # once around the loop
        half = u / 2.0                     # the half-twist
        ch, sh, cu, su = cos(half), sin(half), cos(u), sin(u)
        across = range(strokes_across + 1) if iu % 2 == 0 else range(strokes_across, -1, -1)
        for iv in across:
            v = -width / 2 + width * (iv / strokes_across)   # across the ribbon
            rad = loop_radius + v * ch
            steps.append(fc.Point(x=cx + rad * cu, y=cy + rad * su, z=base_z + v * sh))
    return steps


if __name__ == '__main__':
    steps = mobius_band()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='mobius_band',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote mobius_band.gcode')
