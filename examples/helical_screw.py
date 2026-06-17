"""Helical screw / auger - a vase-mode rod whose wall carries a helical thread.

A continuous spiral whose radius is modulated by a triangular thread profile whose phase advances
with BOTH angle (so the thread wraps the rod) and height (so it climbs as a helix): one or more
thread `starts`, a `pitch` (mm of rise per thread turn) and a `thread_depth`. Shallow + fine = a
screw; deep + coarse + a tapering core = an auger-like flight. The steeper the thread, the more
overhang it asks of the printer - a good non-trivial test piece, still one seamless toolpath.
"""
from math import tau, floor

import fullcontrol as fc


def helical_screw(radius: float = 12.0, height: float = 40.0, pitch: float = 8.0,
                  thread_depth: float = 2.5, starts: int = 1, core_taper: float = 0.0,
                  layer_height: float = 0.24, segments_per_layer: int = 160,
                  extrusion_width: float = 0.6, centre=(50.0, 50.0),
                  first_layer_gap: float = 0.8) -> list:
    """Build a helical-thread rod.

    radius: core radius before the thread (mm).
    pitch: height the thread climbs per full turn (mm) - smaller = steeper/denser thread.
    thread_depth: how far the thread ridge stands out from the core (mm).
    starts: number of independent thread starts (1 = single helix, 2 = double, ...).
    core_taper: 0 = straight rod; up to 1 narrows the core to a point at the top (auger-like).
    """
    cx, cy = centre
    eh = layer_height
    total_segments = max(1, int((height / eh) * segments_per_layer))
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh
        phase = (angle * starts) / tau - h / pitch        # thread periods at this angle & height
        ridge = 1.0 - 2.0 * abs((phase - floor(phase)) - 0.5)   # triangle 0..1, peak mid-period
        core = radius * (1.0 - core_taper * (h / height))
        r = core + thread_depth * ridge
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = helical_screw(starts=2, thread_depth=3, pitch=10)
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='helical_screw',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote helical_screw.gcode')
