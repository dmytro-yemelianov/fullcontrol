"""Freeform Frosting - a decorative swirled column, like piped frosting or a soft-serve swirl.

A reimplementation of FullControl's "Freeform Frosting Challenge". The nozzle traces one
continuous vase-mode spiral whose radius does three things at once as it climbs: it *tapers*
from a wide base toward the top (optionally to a point - the soft-serve tip), it *undulates*
with a set of vertical ripples (the fluted frosting ridges), and the whole ripple pattern
*swirls* - its phase advances with height so the ridges wind around the column like a piped
swirl rather than sitting as straight flutes. A `concave_offset` lets the silhouette bulge out
or pull into a waist between base and tip. One seamless bead, no layer changes, no seam.

The catalogue exposes four design sliders (Diameter at top, Concave offset, and two unnamed
"design parameter" sliders) plus two checkboxes (fan-speed and print-speed variation along the
print). They are mirrored here: `top_diameter`, `concave_offset`, `swirl_amplitude` (unnamed #1,
0-100), `height` (unnamed #2, 10-50), `vary_fan` and `vary_speed`.
"""
from math import tau, sin, pi

import fullcontrol as fc


def freeform_frosting(base_radius: float = 15.8, height: float = 50.0, top_diameter: float = 0.0,
                      concave_offset: float = -1.0, swirls: int = 3, swirl_amplitude: float = 50.0,
                      swirl_turns: float = 4.7, peak: bool = True, vary_fan: bool = False,
                      vary_speed: bool = False, layer_height: float = 0.3,
                      segments_per_layer: int = 128, extrusion_width: float = 0.6,
                      centre=(50.0, 50.0), first_layer_gap: float = 0.5) -> list:
    """Build a freeform piped-frosting swirl column.

    base_radius: nominal wall radius at the bottom (mm) - the wide foot of the frosting.
    height: total height (mm); maps the catalogue's unnamed slider #2 (range 10-50). Default 50
        reproduces the published gcode: a ~32x32x50 tall, narrow swirled column tapering to a point.
    top_diameter: width of the column at the very top (mm); the catalogue 'Diameter at top'
        slider (0-60). 0 with peak=True closes to a point (the soft-serve tip); larger keeps a
        flat-ish cap.
    concave_offset: pushes the mid-height silhouette out (+) or pulls it into a waist (-), in mm;
        the catalogue 'Concave offset' slider (-20..20). 0 = a straight taper from base to top.
    swirls: number of vertical ripples/ridges around the column (the fluting).
    swirl_amplitude: ripple depth as a percentage 0-100 (catalogue unnamed slider #1); scaled to
        a fraction of base_radius so it reads the same at any size.
    swirl_turns: how many full turns the ripple pattern winds over the whole height (the swirl);
        0 = straight flutes, >0 = a piped/twisting swirl.
    peak: True tapers the radius to a point at the top (overrides top_diameter -> 0 there).
    vary_fan / vary_speed: ramp the cooling fan / print speed up the height (the two checkboxes),
        which simply tightens the bead as the overhang gets harder near the tip.
    layer_height: z rise per full turn (mm). segments_per_layer: polyline resolution per turn.
    extrusion_width / centre / first_layer_gap: print setup.
    """
    cx, cy = centre
    eh = layer_height
    top_radius = 0.0 if peak else max(0.0, top_diameter / 2)
    amp = (swirl_amplitude / 100.0) * base_radius * 0.15   # ripple depth (mm), scaled to size
    total_segments = max(1, int((height / eh) * segments_per_layer))
    base_speed = 1000

    steps: list = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    if vary_fan:
        steps.append(fc.Fan(speed_percent=40))
    if vary_speed:
        steps.append(fc.Printer(print_speed=base_speed))
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        z = frac_turn * eh
        f = min(1.0, z / height)                            # 0 at base, 1 at top

        taper = base_radius + (top_radius - base_radius) * f
        belly = concave_offset * sin(f * pi)               # 0 at both ends, peak at mid-height
        # the ripple pattern swirls: its phase advances with height (swirl_turns), so a fixed
        # ridge winds around the column instead of standing as a straight flute.
        ripple = amp * (1.0 - 0.6 * f) * sin(swirls * (angle - swirl_turns * f * tau))
        r = max(0.05, taper + belly + ripple)
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z + first_layer_gap), r, angle))

        if vary_fan and i % segments_per_layer == 0:        # ramp cooling up the height
            steps.append(fc.Fan(speed_percent=int(40 + 60 * f)))
        if vary_speed and i % segments_per_layer == 0:      # slow down as overhang worsens
            steps.append(fc.Printer(print_speed=int(base_speed * (1.0 - 0.5 * f))))
    return steps


if __name__ == '__main__':
    steps = freeform_frosting()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='freeform_frosting',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote freeform_frosting.gcode')
