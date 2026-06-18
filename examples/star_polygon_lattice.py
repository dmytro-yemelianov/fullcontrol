"""Star-Polygon Lattice - a tiled lattice of regular star polygons {n/k}, traced as one continuous
bead (the FullControl "Star-Polygon Lattice Research" demo, www.tinyurl.com/lattice-research).

A *star polygon* {n/k} places `n` points evenly on a circle and joins every k-th point with a
straight chord; with 1 < k < n/2 and gcd(n, k) == 1 this produces a single self-crossing star drawn
in one closed stroke (e.g. {5/2} = pentagram, {7/3}, {8/3}). Setting k == 1 degenerates to a plain
convex {n}-gon, which is how the published model tiles a flat triangular/polygon lattice.

The "lattice" is a `cols` x `rows` grid of these stars, printed as ONE continuous open bead: each
star is drawn in turn, hopping to its neighbour without retraction, snaking left-to-right then
right-to-left up the grid (a boustrophedon, exactly as in the real g-code). The whole sheet is a
thin planar wall - a single course repeated for `layers` (the real model is flat: ~68 x 30 mm,
2 layers, 0.2 mm tall). The default {6/2} hexagram tiling reproduces the published triangular-mesh
proportions (equilateral cells, ~4.3 mm edges, continuous zig-zag bead).
"""
from math import tau, cos, sin, gcd

import fullcontrol as fc


def _star_polygon(cx: float, cy: float, z: float, radius: float, points: int, step: int,
                  phase: float) -> list:
    """Vertices of one star polygon {points/step} centred at (cx, cy), returned as a closed loop.

    The pen visits vertex 0, then step, then 2*step, ... (mod points), and back to the start. When
    gcd(points, step) == 1 this single stroke touches every vertex once (a true {n/k} star); the
    closed loop is what makes the lattice cell self-contained before hopping to the next cell.
    """
    n = points
    loops = []
    visited = 0
    idx = 0
    # one continuous {n/k} stroke (returns to start after n hops when gcd(n, k) == 1)
    while visited <= n:
        angle = phase + (idx % n) * tau / n
        loops.append(fc.Point(x=cx + radius * cos(angle), y=cy + radius * sin(angle), z=z))
        idx += step
        visited += 1
    return loops


def star_polygon_lattice(points: int = 6, step: int = 2, radius: float = 2.5,
                         cols: int = 9, rows: int = 4, layers: int = 2,
                         extrusion_width: float = 0.5, extrusion_height: float = 0.2,
                         x_start: float = 30.0, y_start: float = 30.0) -> list:
    """Build a tiled star-polygon {points/step} lattice as one continuous bead.

    points (n): vertices of each star (>= 3).
    step (k): chord skip - 1 = plain convex polygon; 2 -> {n/2} (e.g. {5/2} pentagram); the star is
        a single self-crossing stroke when gcd(points, step) == 1.
    radius: circumradius (centre-to-vertex) of each star cell (mm).
    cols, rows: lattice grid size (number of star cells across / up).
    layers: how many planar courses to stack (a thin lattice wall); the real model is 2.
    extrusion_width / extrusion_height: bead cross-section (also the layer z-rise).
    x_start, y_start: bottom-left anchor of the lattice (mm), matching the catalogue's X/Y Start.
    """
    eh = extrusion_height
    # pack the cells on a grid: neighbouring stars share a circumradius gap so beads nearly touch.
    pitch_x = radius * 2.0
    pitch_y = radius * 2.0
    # alternate the star orientation per cell so chords interlock into a lattice rather than islands
    base_phase = tau / 4  # a vertex points "up" - gives the published flat-topped triangular mesh

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for layer in range(layers):
        z = (layer + 1) * eh                       # first course sits one bead off the bed
        for r in range(rows):
            col_order = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)  # boustrophedon
            for c in col_order:
                cx = x_start + radius + c * pitch_x
                cy = y_start + radius + r * pitch_y
                phase = base_phase + ((c + r) % 2) * (tau / (2 * points))  # interlock alternating cells
                steps.extend(_star_polygon(cx, cy, z, radius, points, step, phase))
    return steps


def is_valid_star(points: int, step: int) -> bool:
    'True when {points/step} draws as a single self-crossing star (one continuous closed stroke).'
    return points >= 5 and 1 < step < points / 2 and gcd(points, step) == 1


if __name__ == '__main__':
    steps = star_polygon_lattice(points=5, step=2, radius=4, cols=6, rows=3)
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='star_polygon_lattice',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.5, 'extrusion_height': 0.2}))
    print('wrote star_polygon_lattice.gcode')
