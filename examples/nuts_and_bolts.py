"""Nuts and bolts - a printable threaded bolt: a hex head transitioning into a helical-threaded shaft.

One continuous vase-mode spiral (support-free). The cross-section starts as a regular hexagon for
the head - distance to a polygon edge is apothem / cos(angle folded into one sector), exactly like
twisted_polygon_vase - then, over a short blend, collapses to a circular shaft whose radius is
modulated by a helical V-thread, exactly like helical_screw: a triangular ridge whose phase advances
with BOTH angle (so the thread wraps the shaft) and height (so it climbs as a helix of `thread_pitch`
mm per turn). Optionally a matching hex nut (a short hex prism carrying the same internal-clearance
thread on its bore is out of scope for a single bead, so the nut is the head-shaped companion print).

Reverse-engineered from the published fullcontrol.xyz "Nuts and Bolts" g-code (Generic type): a hex
head ~21mm across flats over the first couple of mm, then a ~6mm shaft (core r~3.0, thread crest
r~3.6 => thread_depth~0.6) carrying a single-start helix of pitch ~1.25mm climbing to ~26mm tall.
"""
from math import tau, pi, cos, floor

import fullcontrol as fc


def _ngon_radius(angle: float, sides: int, circumradius: float) -> float:
    'Distance from centre to a regular polygon edge at `angle` (a vertex sits at angle 0).'
    sector = tau / sides
    apothem = circumradius * cos(pi / sides)
    return apothem / cos((angle % sector) - sector / 2)


def nuts_and_bolts(shaft_diameter: float = 6.0, thread_pitch: float = 1.25,
                   thread_depth: float = 0.6, shaft_length: float = 20.0,
                   head_width: float = 21.0, head_height: float = 4.0,
                   thread_starts: int = 1, head_blend: float = 1.5,
                   layer_height: float = 0.15, segments_per_layer: int = 160,
                   extrusion_width: float = 0.6, centre=(50.0, 50.0),
                   first_layer_gap: float = 0.8) -> list:
    """Build a threaded bolt: a hex head morphing into a helical-threaded shaft, one continuous bead.

    shaft_diameter: nominal diameter of the threaded shaft core (mm); the thread crest stands
        `thread_depth` proud of the core radius.
    thread_pitch: height the thread climbs per full turn (mm) - smaller = finer/denser thread.
    thread_depth: how far the V-thread ridge stands out from the shaft core (mm).
    shaft_length: height of the threaded shaft above the head (mm).
    head_width: hex head size across flats (mm); the across-corners size is head_width/cos(30 deg).
    head_height: height of the hex head before it blends into the shaft (mm).
    thread_starts: number of independent thread starts (1 = single helix, 2 = double, ...).
    head_blend: height over which the hexagon collapses to the round shaft (mm).
    """
    cx, cy = centre
    eh = layer_height
    core = shaft_diameter / 2.0
    # head across-flats -> hexagon apothem; convert to the circumradius _ngon_radius expects.
    head_circumradius = (head_width / 2.0) / cos(pi / 6)
    total_height = head_height + head_blend + shaft_length
    total_segments = max(1, int((total_height / eh) * segments_per_layer))

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh

        # helical V-thread on the shaft core (triangle ridge, climbs with angle and height)
        phase = (angle * thread_starts) / tau + h / thread_pitch
        ridge = 1.0 - 2.0 * abs((phase - floor(phase)) - 0.5)      # triangle 0..1, peak mid-period
        shaft_r = core + thread_depth * ridge

        # hexagon head for the first head_height, then blend to the threaded shaft over head_blend
        if h < head_height:
            r = _ngon_radius(angle, 6, head_circumradius)
        elif h < head_height + head_blend:
            f = (h - head_height) / head_blend                    # 0 at head top, 1 at shaft start
            hex_r = _ngon_radius(angle, 6, head_circumradius)
            r = (1.0 - f) * hex_r + f * shaft_r
        else:
            r = shaft_r

        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = nuts_and_bolts()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='nuts_and_bolts',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.15}))
    print('wrote nuts_and_bolts.gcode')
