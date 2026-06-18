"""Raised dome studs by parking the nozzle and oozing material in place.

`bead_studs` showcases `fc.StationaryExtrusion` (extrude-in-place) - a FullControl capability the
rest of the gallery never demonstrates. Most designs deposit material by *moving* the nozzle along a
path; here, the interesting material is laid down with the nozzle held still. For each stud the
toolpath:

  - travels to the stud's XY with the extruder OFF (`fc.Extruder(on=False)`) at the stud's z height,
  - oozes a controlled volume in place with `fc.StationaryExtrusion(volume=..., speed=...)`, which
    builds a small raised dome / bead with no XY motion,
  - moves on to the next stud.

`fc.StationaryExtrusion` resolves to a `MaterialEvent` in the Toolpath IR, so the oozed volume flows
through gcode (a bare `G1 F.. E..` line), simulation (counts toward `extruded_volume`) and validation
like any other material.

Studs are placed either on a plain `rows` x `cols` grid, or - when a `message` string is given - in
the dot pattern of GRADE-1 BRAILLE, one 2x3 cell per character, so the plate literally reads as
braille. An optional flat base plate (`base_layers` raster-filled layers) is printed first so the
studs sit on a solid, support-free surface. Everything is one continuous, support-free toolpath.
"""
import fullcontrol as fc

# Grade-1 braille: each cell is a 2 (cols) x 3 (rows) matrix of dot positions, numbered
#   1 4
#   2 5
#   3 6
# A character maps to the SET of raised dots. We store each letter as that set of dot numbers.
_BRAILLE = {
    'a': {1}, 'b': {1, 2}, 'c': {1, 4}, 'd': {1, 4, 5}, 'e': {1, 5},
    'f': {1, 2, 4}, 'g': {1, 2, 4, 5}, 'h': {1, 2, 5}, 'i': {2, 4}, 'j': {2, 4, 5},
    'k': {1, 3}, 'l': {1, 2, 3}, 'm': {1, 3, 4}, 'n': {1, 3, 4, 5}, 'o': {1, 3, 5},
    'p': {1, 2, 3, 4}, 'q': {1, 2, 3, 4, 5}, 'r': {1, 2, 3, 5}, 's': {2, 3, 4}, 't': {2, 3, 4, 5},
    'u': {1, 3, 6}, 'v': {1, 2, 3, 6}, 'w': {2, 4, 5, 6}, 'x': {1, 3, 4, 6},
    'y': {1, 3, 4, 5, 6}, 'z': {1, 3, 5, 6},
    ' ': set(),
}

# pixel position (col, row) within a cell for each braille dot number (row 0 = top)
_DOT_XY = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}


def braille_dots(message: str):
    """Map a `message` string to braille stud positions as integer cell coordinates.

    Returns a list of (col, row) tuples, where `col` runs left->right across the whole message
    (each character occupies 2 dot-columns plus a 1-column gap) and `row` runs top->bottom (0..2).
    Unknown characters are treated as a blank cell. Raises if the message has no dots."""
    positions = []
    for ci, ch in enumerate(message.lower()):
        dots = _BRAILLE.get(ch, set())
        cell_x0 = ci * 3  # 2 dot-columns + 1 gap column per character
        for dot in sorted(dots):
            dx, dy = _DOT_XY[dot]
            positions.append((cell_x0 + dx, dy))
    return positions


def bead_studs(message: str = None, rows: int = 3, cols: int = 4, stud_volume: float = 2.0,
               stud_speed: int = 200, spacing: float = 6.0, base_layers: int = 2,
               layer_height: float = 0.3, extrusion_width: float = 0.6, stud_z: float = None,
               base_size: float = None, centre=(100.0, 100.0)) -> list:
    """A field of raised dome studs oozed in place with `fc.StationaryExtrusion`.

    If `message` is given, the studs spell it in grade-1 braille (one 2x3 cell per character);
    otherwise a plain `rows` x `cols` grid of studs is produced. An optional flat base plate of
    `base_layers` raster layers is printed first so the studs sit on a solid surface.

    Args:
        message: text to encode in braille; when None, a `rows` x `cols` grid is used instead.
        rows, cols: grid dimensions (grid mode only).
        stud_volume: mm^3 of material oozed in place per stud (the dome size).
        stud_speed: extrusion feedrate for the stationary ooze.
        spacing: centre-to-centre distance between adjacent studs / braille dots (mm).
        base_layers: number of raster-filled base-plate layers (0 = studs only, no plate).
        layer_height, extrusion_width: extrusion geometry.
        stud_z: z height at which studs are oozed; defaults to just above the base plate.
        base_size: side length of the square base plate; defaults to span the studs + a margin.
        centre: (x, y) centre of the design on the bed.

    Returns a list of FullControl steps beginning with its own `fc.ExtrusionGeometry`."""
    cx, cy = centre

    # stud positions as (col, row) integer cells, then mapped to bed coordinates
    if message is not None:
        cells = braille_dots(message)
        if not cells:
            raise ValueError('message encodes no braille dots')
    else:
        cells = [(c, r) for r in range(rows) for c in range(cols)]

    max_col = max(c for c, _ in cells)
    max_row = max(r for _, r in cells)
    # centre the field of cells about `centre`
    x0 = cx - max_col * spacing / 2.0
    y0 = cy + max_row * spacing / 2.0  # row 0 at the top
    studs = [(x0 + c * spacing, y0 - r * spacing) for c, r in cells]

    if stud_z is None:
        stud_z = max(base_layers, 1) * layer_height  # sit on top of the base plate

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=layer_height)]

    # optional flat base plate: a simple boustrophedon raster fill, a few layers deep
    if base_layers > 0:
        span_x = max_col * spacing
        span_y = max_row * spacing
        if base_size is not None:
            half_x = half_y = base_size / 2.0
        else:
            half_x = span_x / 2.0 + spacing
            half_y = span_y / 2.0 + spacing
        bx0, bx1 = cx - half_x, cx + half_x
        by0, by1 = cy - half_y, cy + half_y
        line_pitch = extrusion_width
        n_lines = max(2, int((by1 - by0) / line_pitch) + 1)
        for layer in range(base_layers):
            z = (layer + 1) * layer_height
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=bx0, y=by0, z=z))
            steps.append(fc.Extruder(on=True))
            for i in range(n_lines):
                y = by0 + i * (by1 - by0) / (n_lines - 1)
                # alternate sweep direction each raster line (boustrophedon)
                if i % 2 == 0:
                    steps.append(fc.Point(x=bx0, y=y, z=z))
                    steps.append(fc.Point(x=bx1, y=y, z=z))
                else:
                    steps.append(fc.Point(x=bx1, y=y, z=z))
                    steps.append(fc.Point(x=bx0, y=y, z=z))

    # the studs: park the nozzle and ooze a dome in place
    for sx, sy in studs:
        steps.append(fc.Extruder(on=False))                  # travel to the stud, no extrusion
        steps.append(fc.Point(x=sx, y=sy, z=stud_z))
        steps.append(fc.StationaryExtrusion(volume=stud_volume, speed=stud_speed))  # ooze in place

    return steps


if __name__ == '__main__':
    steps = bead_studs(message='fc')
    n_studs = sum(1 for s in steps if isinstance(s, fc.StationaryExtrusion))
    print(f"bead_studs('fc'): {len(steps)} steps, {n_studs} stationary-extrusion studs")
