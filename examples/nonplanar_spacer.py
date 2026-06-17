"""Non-planar wavy washer/spacer - a reimplementation of models/nonplanar_spacer.ipynb.

A flat washer is printed as concentric rings, but every ring's z follows a sinusoidal wave around
the circumference (`waves` crests). Because z varies *within* each ring, this is a genuinely
non-planar toolpath - the whole part is one continuous spiral of rings that ramp up in wave height
from the bed to the full thickness. A pointy nozzle is needed so it can dip into the troughs.
"""
from math import tau, cos

import fullcontrol as fc


def nonplanar_spacer(inner_diameter: float = 15.0, outer_diameter: float = 30.0,
                     total_thickness: float = 3.0, waves: int = 3, wave_contraction: float = 0.5,
                     layer_height: float = 0.3, ew_eh_ratio: float = 2.5, overlap_percent: float = 20.0,
                     centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """Concentric non-planar rings from inner_diameter to outer_diameter.

    waves: number of sinusoidal crests around the ring.
    wave_contraction: pulls higher parts of a wave radially inward (counters nozzle drag on slopes).
    overlap_percent: radial overlap between adjacent rings (bonding).
    """
    cx, cy = centre
    eh = layer_height
    ew = eh * ew_eh_ratio
    overlap = (overlap_percent / 100) * ew
    wave_height = total_thickness - eh
    r1, r2 = inner_diameter / 2, outer_diameter / 2
    rings = max(1, int((r2 - r1) / (ew - overlap)))
    segs_per_ring = (waves * 2) * max(1, int(128 / (waves * 2)))  # a node exactly at each crest/trough

    centre_pt = fc.Point(x=cx, y=cy, z=first_layer_gap)
    steps = [fc.ExtrusionGeometry(width=ew, height=eh)]
    for ring in range(rings):
        for seg in range(segs_per_ring + 1):
            angle = (seg / segs_per_ring) * tau
            z = wave_height * (ring / max(1, rings - 1)) * (0.5 - 0.5 * cos(angle * waves))
            radius = r1 + ew / 2 + ring * (ew - overlap) - (z * wave_contraction)
            centre_pt.z = z + first_layer_gap
            steps.append(fc.polar_to_point(centre_pt, radius, angle))
    return steps


if __name__ == '__main__':
    steps = nonplanar_spacer()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='nonplanar_spacer',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.75, 'extrusion_height': 0.3}))
    print('wrote nonplanar_spacer.gcode')
