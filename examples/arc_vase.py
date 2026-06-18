"""A vase whose every layer is a closed loop of true ``fc.Arc`` (G2/G3) moves.

Each layer is a scalloped (petal) cross-section built from ``petals`` tangent circular arcs.
The N vertices sit evenly on a circle of ``radius``; consecutive vertices are joined by a single
circular arc that bows outward (a petal) or inward (a scallop) by ``scallop_depth``. So one layer
is just ``petals`` G2/G3 commands - a handful of arc moves - instead of the hundreds of short line
segments a segmented vase of the same fidelity would need. The g-code is tiny and the curves are
glass-smooth (the printer interpolates the arc, not FullControl).

The vase is HELICAL / vase-mode: every arc advances z by a slice of the layer height (each arc's
``end`` carries a differing z), so the wall climbs as one continuous spiral of arcs with no seam and
no layer change. Support-free single bead.
"""
from math import cos, hypot, sin, tau

import fullcontrol as fc


def _vertex(cx: float, cy: float, radius: float, angle: float) -> fc.Point:
    'A point on the base circle at the given angle (z filled in later by the caller).'
    return fc.Point(x=cx + radius * cos(angle), y=cy + radius * sin(angle))


def _arc_centre(sx: float, sy: float, ex: float, ey: float, scallop_depth: float,
                bulge_out: bool):
    '''Centre of the circular arc through (sx,sy)->(ex,ey) with sagitta ``scallop_depth``.

    The arc bows away from the chord by ``scallop_depth`` (outward for a petal, inward for a
    scallop). Returns (cx, cy, clockwise) where ``clockwise`` is the G2/G3 direction that draws the
    bowed (minor) arc in the chord's travel direction.
    '''
    mx, my = (sx + ex) / 2, (sy + ey) / 2          # chord midpoint
    half_chord = hypot(ex - sx, ey - sy) / 2
    s = max(scallop_depth, 1e-6)                    # sagitta (keep strictly positive)
    arc_r = (half_chord ** 2 + s ** 2) / (2 * s)   # radius of the circle giving that sagitta
    # unit vector along the chord, and its left-hand normal
    ux, uy = (ex - sx) / (2 * half_chord), (ey - sy) / (2 * half_chord)
    nx, ny = -uy, ux
    # the centre sits on the far side of the chord from the bulge, at distance (arc_r - sagitta)
    d = arc_r - s
    sign = -1.0 if bulge_out else 1.0              # which side the bulge (and so the centre) is on
    cx = mx + sign * nx * d
    cy = my + sign * ny * d
    # travelling start->end, an outward bulge sweeps clockwise; inward sweeps anticlockwise
    return cx, cy, arc_r, bulge_out


def arc_vase(petals: int = 6, radius: float = 22.0, scallop_depth: float = 5.0,
             height: float = 40.0, layer_height: float = 0.3, bulge_out: bool = True,
             extrusion_width: float = 0.6, centre=(100.0, 100.0),
             first_layer_gap: float = 0.8) -> list:
    """Build a helical scalloped vase made entirely of native ``fc.Arc`` moves.

    petals: number of arcs per layer (the lobe count of the cross-section). >= 2.
    radius: radius of the circle the petal vertices sit on (mm).
    scallop_depth: how far each arc bows off its chord (mm); ``bulge_out`` picks in/out.
    height: total vase height (mm).
    layer_height: z rise per full turn (the effective layer height, mm).
    bulge_out: True = convex petals (G2), False = concave scallops (G3).
    extrusion_width / first_layer_gap / centre: print setup.

    Returns a list of FullControl steps starting with its own ``fc.ExtrusionGeometry``; every wall
    move is an ``fc.Arc`` (one G2/G3 each), so each layer is exactly ``petals`` arc commands.
    """
    if petals < 2:
        raise ValueError('petals must be >= 2 to form a closed cross-section')
    cx, cy = centre
    eh = layer_height
    turns = max(1, round(height / eh))
    dz_per_arc = eh / petals                        # each arc climbs a fraction of the layer
    base_angles = [i / petals * tau for i in range(petals)]

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    # start the bead at the first vertex of the first layer
    start = _vertex(cx, cy, radius, base_angles[0])
    z = first_layer_gap
    steps.append(fc.Point(x=start.x, y=start.y, z=z))

    total_arcs = turns * petals
    for k in range(total_arcs):
        a0 = base_angles[k % petals]
        a1 = base_angles[(k + 1) % petals]
        sx = cx + radius * cos(a0)
        sy = cy + radius * sin(a0)
        ex = cx + radius * cos(a1)
        ey = cy + radius * sin(a1)
        ccx, ccy, _r, out = _arc_centre(sx, sy, ex, ey, scallop_depth, bulge_out)
        z += dz_per_arc                             # helical: end z is a touch above start z
        direction = 'clockwise' if out else 'anticlockwise'
        steps.append(fc.Arc(centre=fc.Point(x=ccx, y=ccy),
                            end=fc.Point(x=ex, y=ey, z=z), direction=direction))
    return steps


if __name__ == '__main__':
    steps = arc_vase()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='arc_vase',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote arc_vase.gcode')
