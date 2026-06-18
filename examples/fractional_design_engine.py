"""A flat polar design engine - trace a parametric curve r(theta) over fractional turns.

This is a faithful, parametric reimplementation of FullControl's "Fractional Design Engine (Polar)"
(fullcontrol.xyz model a72616). The original is dead simple: you hand it a list of *fractional*
polar angles and a matching list of *fractional* radii, and it plots `(radius_fraction * radius,
angle_fraction * 2*pi)` for each pair and connects the dots into a flat lattice.

The reference g-code is the classic 11-point alternating star: `angle_fractions = 0,0.1,...,1.0`
(eleven evenly spaced fractions of one full turn) and `radial_fractions = 1,0.5,1,0.5,...,1`
(alternating outer/inner radius), at `radius = 20` about centre `(50, 50)` - a 5-pointed polar
star. That star is the published model's signature output, so it is the **default** here: call
`fractional_design_engine()` with no arguments and you get exactly that star.

The engine also generalises into a proper *design engine*:

  * `mode='star'` (default) traces an n-pointed alternating-radii star,
  * `mode='rose'` traces a parametric polar **rose** `r = radius * |cos(petals * theta)|`,
  * supplying explicit `radial_fractions` + `angle_fractions` reproduces the original model exactly,
  * `turns` is a true *fractional* turn count - the angular span is `turns * 2*pi`,
  * `points` sets the resolution, and `layers` stacks the flat pattern into a few layers.

Everything stays flat (constant z per layer), matching the flat polar nature of the original.

    from examples import fractional_design_engine
    steps = fractional_design_engine()                 # the reference 5-point star
    steps = fractional_design_engine(mode='rose', petals=5, radius=20)
"""
from math import cos, tau

import fullcontrol as fc


def fractional_design_engine(radius: float = 20.0, mode: str = 'star', star_points: int = 5,
                             inner_fraction: float = 0.5, petals: int = 5, turns: float = 1.0,
                             points: int = None, layers: int = 1,
                             radial_fractions: list = None, angle_fractions: list = None,
                             centre=(50.0, 50.0), extrusion_width: float = 0.6,
                             extrusion_height: float = 0.2, first_layer_gap: float = 0.0,
                             close: bool = True) -> list:
    """Build a flat polar lattice - by default the reference alternating-radii star.

    radius: scale of the design (mm) - the maximum radial extent.
    mode: 'star' (default) or 'rose'. Ignored when explicit fraction lists are supplied.
        'star' draws an `star_points`-pointed star whose vertices alternate between `radius`
        (outer tips) and `inner_fraction * radius` (inner vertices). With the defaults this is
        the published model: a 5-point star at radius 20 about (50, 50).
        'rose' traces a polar rose `r = radius*|cos(petals*theta)|`.
    star_points: number of outer points of the star (mode='star').
    inner_fraction: inner-vertex radius as a fraction of `radius` (mode='star'); 0.5 -> half.
    petals: rose frequency `k` in `r = radius*|cos(k*theta)|` (mode='rose'); gives `petals` (odd)
        or `2*petals` (even) radial maxima around the centre.
    turns: number of *fractional* turns to sweep; the angular span is `turns * 2*pi` (so 0.5 is a
        half turn, 1.5 is one and a half). This is the "fractional" essence of the engine.
    points: polyline resolution. Defaults to `2*star_points + 1` for the star (one control point
        per vertex plus the closing point) and 240 for the rose. Pass an explicit value to
        resample - the star is re-traced with that many evenly spaced control points.
    layers: how many flat layers to stack (each raised by `extrusion_height`).
    radial_fractions / angle_fractions: optional explicit control-point lists, exactly like the
        original model. `angle_fractions` are fractions of a full turn (0..1 -> 0..2*pi) and
        `radial_fractions` are fractions of `radius`. When given, they override the generators
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
    elif mode == 'star':
        if star_points < 2:
            raise ValueError('star_points must be >= 2')
        # the reference model: 2*star_points alternating outer/inner vertices over one full turn,
        # expressed as fractional radii (1, inner_fraction, 1, ...) and fractional angles.
        n = 2 * star_points
        # default resolution = one control point per vertex (+ closing point added below);
        # an explicit `points` resamples to that many evenly spaced control points.
        count = n if points is None else max(2, points)
        angles, radii = [], []
        for i in range(count):
            frac = i / count                            # 0..1 around one full turn (exclusive end)
            theta = frac * turns * tau
            rf = 1.0 if (round(frac * n) % 2 == 0) else inner_fraction
            angles.append(theta)
            radii.append(rf * radius)
    elif mode == 'rose':
        rose_points = 240 if points is None else points
        if rose_points < 2:
            raise ValueError('points must be >= 2')
        span = turns * tau
        angles, radii = [], []
        for i in range(rose_points):
            frac = i / (rose_points - 1)                # 0..1 along the sweep
            theta = frac * span
            angles.append(theta)
            radii.append(radius * abs(cos(petals * theta)))
    else:
        raise ValueError("mode must be 'star' or 'rose'")

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
