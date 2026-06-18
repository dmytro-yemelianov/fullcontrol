"""A flat polar design engine - trace a parametric curve r(theta) over fractional turns.

This is a faithful, parametric reimplementation of FullControl's "Fractional Design Engine (Polar)"
(fullcontrol.xyz model a72616). The original is dead simple: you hand it a list of *fractional*
polar angles and a matching list of *fractional* radii, and it plots `(radius_fraction * radius,
angle_fraction * 2*pi)` for each pair and connects the dots into a flat lattice. The reference
g-code is the classic 11-point alternating star (radial_fractions = 1,0.5,1,0.5,... over one full
turn) - a 5-pointed star drawn in polar coordinates.

This implementation keeps that exact behaviour (pass `radial_fractions` + `angle_fractions` and the
points land at those polar coords) and generalises it into a proper *design engine*:

  * give it nothing and it traces a parametric polar **rose** `r = radius * |cos(petals * theta)|`,
  * `turns` is a true *fractional* turn count - the angular span is `turns * 2*pi`,
  * `points` sets the resolution, and `layers` stacks the flat pattern into a few layers.

Everything stays flat (constant z per layer), matching the flat polar nature of the original.

    from examples import fractional_design_engine
    steps = fractional_design_engine(petals=5, radius=20)
"""
from math import cos, tau

import fullcontrol as fc


def fractional_design_engine(radius: float = 20.0, petals: int = 5, turns: float = 1.0,
                             points: int = 240, layers: int = 1,
                             radial_fractions: list = None, angle_fractions: list = None,
                             centre=(50.0, 50.0), extrusion_width: float = 0.6,
                             extrusion_height: float = 0.2, first_layer_gap: float = 0.0,
                             close: bool = True) -> list:
    """Build a flat polar lattice / rose.

    radius: scale of the design (mm) - the maximum radial extent.
    petals: rose frequency `k` in `r = radius*|cos(k*theta)|`; gives `petals` (odd) or `2*petals`
        (even) radial maxima around the centre. Ignored when explicit lists are supplied.
    turns: number of *fractional* turns to sweep; the angular span is `turns * 2*pi` (so 0.5 is a
        half turn, 1.5 is one and a half). This is the "fractional" essence of the engine.
    points: polyline resolution (number of control points along the curve).
    layers: how many flat layers to stack (each raised by `extrusion_height`).
    radial_fractions / angle_fractions: optional explicit control-point lists, exactly like the
        original model. `angle_fractions` are fractions of a full turn (0..1 -> 0..2*pi) and
        `radial_fractions` are fractions of `radius`. When given, they override the rose generator
        and the points land precisely at those polar coordinates.
    centre: (x, y) centre of the design (mm).
    extrusion_width / extrusion_height: bead size (mm).
    first_layer_gap: z offset added to the first layer (mm).
    close: if True, repeat the first control point at the end so the loop closes.
    """
    cx, cy = centre

    if angle_fractions is not None or radial_fractions is not None:
        if angle_fractions is None or radial_fractions is None:
            raise ValueError('supply both angle_fractions and radial_fractions, or neither')
        if len(angle_fractions) != len(radial_fractions):
            raise ValueError('angle_fractions and radial_fractions must be the same length')
        angles = [af * tau for af in angle_fractions]
        radii = [rf * radius for rf in radial_fractions]
    else:
        if points < 2:
            raise ValueError('points must be >= 2')
        span = turns * tau
        angles, radii = [], []
        for i in range(points):
            frac = i / (points - 1)            # 0..1 along the sweep
            theta = frac * span
            angles.append(theta)
            radii.append(radius * abs(cos(petals * theta)))

    if close and (radii[0] != radii[-1] or angles[0] != angles[-1]):
        angles = angles + [angles[0]]
        radii = radii + [radii[0]]

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=extrusion_height)]
    for layer in range(max(1, layers)):
        z = first_layer_gap + layer * extrusion_height
        centre_pt = fc.Point(x=cx, y=cy, z=z)
        for r, theta in zip(radii, angles):
            steps.append(fc.polar_to_point(centre_pt, r, theta))
    return steps


if __name__ == '__main__':
    steps = fractional_design_engine()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='fractional_design_engine',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.2}))
    print('wrote fractional_design_engine.gcode')
