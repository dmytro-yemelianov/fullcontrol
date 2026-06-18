"""Snake-Mode Soapdish - a corrugated open wall printed like FullControl's Snake-Mode Soapdish.

'Snake mode' is vase mode for *open* structures: print one way, step the nozzle up, print back,
step up, repeat. The result here is a single corrugated wall - a sine-wave footprint of `waves`
corrugations that snakes there-and-back, course by course, climbing in z. The wall's horizontal
length swells from the base to mid-height and tapers again toward the top (a lens / leaf
silhouette), and its baseline is gently bowed, so the soap rests in the wavy cradle and water drains
through the corrugations.

Print it with FAT layers - snake mode loves volumetric flow. The reference settings lay 1-mm-wide
lines (nozzle 0.4-1 mm all work), about 0.33 mm tall, run hot (try +20 C) and fast (speed 200%);
volumetric flow ~2.5 mm^3/s. One seamless, support-free, open bead.

This reimplements the real FullControl model (an open corrugated wall) - NOT a closed cup; verified
against the published g-code (60 mm wide x ~100 mm tall, 8 corrugations, lens silhouette).
"""
from math import tau, sin, sqrt

import fullcontrol as fc


def _lens(u: float) -> float:
    'Silhouette factor over normalised height u in [0, 1]: 0 at the ends, 1 at mid-height.'
    return sqrt(max(0.0, 1.0 - (2.0 * u - 1.0) ** 2))


def snake_soapdish(length: float = 60.0, height: float = 100.0, waves: int = 8,
                   amplitude: float = 6.0, end_scale: float = 0.67, bow: float = 2.5,
                   layer_height: float = 0.333, points_per_wave: int = 17,
                   extrusion_width: float = 1.0, centre=(70.0, 48.6),
                   first_layer_gap: float = 0.6) -> list:
    """Build a snake-mode soapdish: a corrugated open wall with a lens silhouette.

    length: horizontal span at mid-height (mm); waves: number of corrugations across the wall;
    amplitude: corrugation depth at mid-height (mm); end_scale: span/amplitude at the top and bottom
    as a fraction of mid-height (gives the lens / leaf silhouette); bow: how far the baseline arcs
    (mm); layer_height: z-step between snake courses (also the fat bead height). Snake mode reverses
    the traverse each course; z climbs monotonically (it does not zig-zag in z).
    """
    cx, cy = centre
    eh = layer_height
    courses = max(2, int(round(height / eh)))
    per = waves * points_per_wave
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for k in range(courses):
        z = first_layer_gap + k * eh
        u = k / (courses - 1)
        s = end_scale + (1.0 - end_scale) * _lens(u)            # lens: swell to mid, taper to ends
        amp = amplitude * s
        forward = (k % 2 == 0)                                  # the snake reverses each course
        for j in range(per + 1):
            t = j / per
            tt = t if forward else 1.0 - t
            along = (tt - 0.5) * length * s                     # traverse across the wall
            baseline = -bow * s * (1.0 - (2.0 * tt - 1.0) ** 2)  # gentle bow, dipping in the middle
            wave = amp * sin(tau * waves * tt)                  # the corrugations
            steps.append(fc.Point(x=cx + along, y=cy + baseline + wave, z=z))
    return steps


if __name__ == '__main__':
    steps = snake_soapdish()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='snake_soapdish',
        initialization_data={'nozzle_temp': 230, 'bed_temp': 50, 'primer': 'front_lines_then_y',
                             'extrusion_width': 1.0, 'extrusion_height': 0.333,
                             'print_speed': 4000}))   # fat, hot, fast - snake mode loves flow
    print('wrote snake_soapdish.gcode')
