"""Wrap a flat texture onto a surface of revolution - a reusable non-planar mapping helper.

`revolve(profile, texture, ...)` traces a vase-mode spiral whose radius is `profile(height_fraction)`
plus a `texture(around, up)` displacement, so any 2-D pattern in the (around-the-part, up-the-part)
unit square is conformed to a cone / cylinder / barrel / custom profile. It generalises the
hand-rolled radial maths in nonplanar_spacer and the vases into one parametric transform.

`textured_cone` is a concrete gallery design built on it: a tapering cone carrying an egg-crate
diamond grid. Define your own with two small lambdas:

    from examples.surface_texture import revolve
    from math import cos, tau
    steps = revolve(profile=lambda f: 20 - 12*f,                 # cone: 20 mm -> 8 mm
                    texture=lambda u, v: cos(tau*8*u)*cos(tau*10*v))   # a wrapped checker
"""
from math import tau, cos

import fullcontrol as fc


def revolve(profile, texture=None, height: float = 40.0, texture_depth: float = 1.5,
            layer_height: float = 0.24, segments_per_layer: int = 128,
            extrusion_width: float = 0.6, centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """Vase-mode spiral on a surface of revolution.

    profile(f): base radius (mm) at height fraction f in [0, 1] (a cylinder is `lambda f: R`).
    texture(around, up): displacement in roughly [-1, 1] for around/up both in [0, 1]; None = smooth.
    texture_depth: scales the displacement (mm).
    """
    cx, cy = centre
    eh = layer_height
    total_segments = max(1, int((height / eh) * segments_per_layer))
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac_turn = i / segments_per_layer
        angle = frac_turn * tau
        h = frac_turn * eh
        f = min(1.0, h / height)
        r = profile(f)
        if texture is not None:
            r += texture_depth * texture(frac_turn % 1.0, f)
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=h + first_layer_gap), r, angle))
    return steps


def textured_cone(base_radius: float = 20.0, top_radius: float = 8.0, height: float = 35.0,
                  cells_around: int = 8, cells_up: int = 10, texture_depth: float = 1.2,
                  layer_height: float = 0.24, segments_per_layer: int = 160,
                  extrusion_width: float = 0.6, centre=(50.0, 50.0),
                  first_layer_gap: float = 0.8) -> list:
    """A cone (base_radius -> top_radius) wrapped in an egg-crate diamond grid of `cells_around` x
    `cells_up` bumps - a worked example of `revolve`."""
    def profile(f):
        return base_radius + (top_radius - base_radius) * f

    def texture(u, v):
        return (cos(tau * cells_around * u) + cos(tau * cells_up * v)) / 2.0

    return revolve(profile, texture, height=height, texture_depth=texture_depth,
                   layer_height=layer_height, segments_per_layer=segments_per_layer,
                   extrusion_width=extrusion_width, centre=centre, first_layer_gap=first_layer_gap)


if __name__ == '__main__':
    steps = textured_cone()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='textured_cone',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.24}))
    print('wrote textured_cone.gcode')
