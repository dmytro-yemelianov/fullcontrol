"""Wavy-rim bowl - a NEW design (not in the original models/), built on the vase-mode spiral.

Demonstrates combining two ideas from the reimplemented demos: a continuous vase-mode spiral
(spiral_vase) whose *radius follows a curved wall profile* so the cross-section flares like a bowl,
plus a sinusoidal rim wave (nonplanar_spacer) whose amplitude grows toward the top - so the base is
a clean circle and only the lip ripples. A single seamless toolpath.
"""
from math import tau, sin, pi

import fullcontrol as fc


def wave_bowl(opening_radius: float = 25.0, base_radius: float = 6.0, height: float = 20.0,
              rim_waves: int = 6, rim_wave_amplitude: float = 3.0, flare: float = 1.0,
              layer_height: float = 0.24, segments_per_layer: int = 160,
              extrusion_width: float = 0.6, centre=(50.0, 50.0),
              first_layer_gap: float = 0.8) -> list:
    """A bowl whose wall radius flares from base_radius to opening_radius up the height.

    flare: wall-profile shape. 1.0 = quarter-sine (hemispherical bowl); <1 = straighter/conical
        walls; >1 = the flare happens later (deeper cup).
    rim_waves / rim_wave_amplitude: number and size of the lip ripples (amplitude ramps in as the
        square of height, so the base stays a clean circle).
    """
    cx, cy = centre
    eh = layer_height
    turns = height / eh
    total_segments = max(1, int(turns * segments_per_layer))
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh                       # height above bed
        f = min(1.0, h / height)                 # 0 at base, 1 at rim
        wall = base_radius + (opening_radius - base_radius) * sin(f * pi / 2) ** flare
        rim = rim_wave_amplitude * (f * f) * sin(rim_waves * angle)
        r = wall + rim
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


if __name__ == '__main__':
    steps = wave_bowl()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='wave_bowl',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote wave_bowl.gcode')
