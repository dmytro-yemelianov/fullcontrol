"""Snake-mode soapdish - an open, spiky-rimmed cup, printed like FullControl's Snake-Mode Soapdish.

"Snake mode" is vase mode for open structures: print one way, move up, print back, move up, repeat.
Here the nozzle snakes around the cup wall while its z zig-zags up to a spike and back down (`waves`
spikes around the rim); the zig-zag amplitude is zero through the solid base and ramps in above it,
so the wall is solid at the bottom and opens into a crown of vertical spikes at the top. The spikes
stay angularly aligned course to course (vertical spikes, not a crossing lattice). Print it fast with
fat lines (snake mode loves volumetric flow). One seamless, support-free bead.
"""
from math import tau, sin, cos, floor

import fullcontrol as fc


def snake_soapdish(radius: float = 24.0, height: float = 26.0, waves: int = 12,
                   spike_height: float = 10.0, base_height: float = 4.0, layer_height: float = 0.4,
                   points_per_wave: int = 14, extrusion_width: float = 1.0,
                   centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """Build a snake-mode soapdish.

    radius: cup wall radius (mm); waves: number of rim spikes; spike_height: how far the crown
    spikes rise above the wall (mm); base_height: solid (un-spiked) wall height before the spikes
    ramp in (mm); layer_height: vertical step between snake courses (also the bead height).
    """
    cx, cy = centre
    eh = layer_height
    courses = max(1, int(round(height / eh)))
    ramp = max(1e-6, height - base_height)
    per = waves * points_per_wave
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for k in range(courses):
        z0 = first_layer_gap + k * eh
        amp = spike_height * max(0.0, (k * eh - base_height)) / ramp   # 0 over the base, ramps in
        forward = (k % 2 == 0)                                          # the snake: reverse each course
        for j in range(per + 1):
            f = j / per
            af = f if forward else 1.0 - f
            phi = af * tau
            ph = waves * af
            tri = 1.0 - 2.0 * abs((ph - floor(ph)) - 0.5)              # 0..1 spike profile (aligned)
            steps.append(fc.Point(x=cx + radius * cos(phi), y=cy + radius * sin(phi), z=z0 + amp * tri))
    return steps


if __name__ == '__main__':
    steps = snake_soapdish()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='snake_soapdish',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 1.0, 'extrusion_height': 0.4}))
    print('wrote snake_soapdish.gcode')
