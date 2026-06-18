"""2000-Retractions Test - a flat retraction calibration/stress test.

Reimplementation of FullControl's "2000-Retractions Test" demo (fullcontrol.xyz model `3bfcdb`,
"Test lots of retraction settings under lots of printing conditions"). The original prints a flat
single-layer field of short extruded marks and hops between them, performing a configurable - and
deliberately large - number of retractions in well under an hour, so you can dial in retraction
distance/speed against stringing.

Reverse-engineered from `2000-retractions-test.gcode` (986 extruding points, bbox ~178x146x0.2mm -
essentially flat / single layer): the toolpath is a serpentine field of short straight marks at a
sequence of Y positions, each travel between marks bracketed by a firmware retraction (`G10`) and an
unretraction (`G11`) - 551 G10/G11 pairs in the captured file. This reimplementation does the same
thing with explicit FullControl retraction steps: every inter-mark travel is guarded by an
`fc.Retraction` / `fc.Unretraction` pair (with the extruder lifted and turned off across the hop), so
the print performs exactly `retractions` retractions.

The design is parametric on the retraction count itself (`retractions`), plus the mark geometry
(`mark_length`, `spacing`), the retraction tuning under test (`retraction_distance`,
`retraction_speed`), and the flat-field knobs that mirror the original's sliders/checkboxes
(`layers`, `z_offset`, and the `fewer_*` shrink switches). `retraction_test()` returns a plain list
of FullControl steps starting with its own `fc.ExtrusionGeometry`, ready for any backend.
"""
import fullcontrol as fc


def retraction_test(retractions: int = 240, mark_length: float = 12.0, spacing: float = 3.0,
                    retraction_distance: float = 1.0, retraction_speed: float = 2000.0,
                    travel_lift: float = 0.6, cols: int | None = None, layers: int = 1,
                    z_offset: float = 0.0, layer_height: float = 0.2, extrusion_width: float = 0.4,
                    centre=(100.0, 75.0), fewer_sets: bool = False, fewer_travel_lines: bool = False,
                    fewer_lines_per_set: bool = False) -> list:
    """A flat field of short extruded marks separated by retraction-guarded travels.

    The print lays down `retractions + 1` short marks (so there are exactly `retractions` travels,
    each bracketed by an `fc.Retraction`/`fc.Unretraction` pair) over `layers` flat layers. Marks are
    arranged left-to-right / right-to-left in rows (a serpentine field) to keep travels short, exactly
    like the original retraction stress test.

    Args:
        retractions: target number of retractions to perform (== number of inter-mark travels). The
            real model targets ~2000; the default is a smaller, fast field.
        mark_length: length (mm) of each short extruded mark.
        spacing: row-to-row gap (mm) between marks (the serpentine pitch in Y).
        retraction_distance: filament length (mm) to retract before each travel - the value under test.
        retraction_speed: retraction/unretraction feedrate (mm/min).
        travel_lift: z-hop (mm) applied across each travel to avoid dragging the nozzle.
        cols: marks per row; if None a roughly square field is chosen automatically.
        layers: number of (flat) layers - the field is repeated this many times up the z axis.
        z_offset: constant z shift (mm) added to every move (mirrors the model's Z Offset slider).
        layer_height: layer height (mm); also the first-layer gap above the bed.
        extrusion_width: extrusion width (mm).
        centre: (x, y) centre of the field on the bed.
        fewer_sets: shrink switch - halve the marks-per-row (fewer columns / sets).
        fewer_travel_lines: shrink switch - widen `spacing` so fewer rows are needed.
        fewer_lines_per_set: shrink switch - halve `mark_length` (shorter marks).

    Returns:
        list: FullControl steps beginning with an `fc.ExtrusionGeometry`.
    """
    if retractions < 1:
        raise ValueError('retractions must be >= 1')

    if fewer_lines_per_set:
        mark_length = mark_length / 2.0
    if fewer_travel_lines:
        spacing = spacing * 2.0

    n_marks = retractions + 1                       # N marks -> N-1 travels; per-layer count below
    cx, cy = centre

    # marks-per-row: a roughly square field unless the caller fixes `cols`
    if cols is None:
        cols = max(1, round(n_marks ** 0.5))
    if fewer_sets:
        cols = max(1, cols // 2)

    half = mark_length / 2.0
    x_left = cx - half
    x_right = cx + half

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=layer_height)]
    travels = 0                                     # retraction-guarded hops actually emitted
    placed = 0                                      # marks placed so far (across all layers)
    first = True

    for layer in range(layers):
        z = z_offset + layer_height + layer * layer_height
        # how many marks this layer should hold (spread the total field over the layers)
        remaining_layers = layers - layer
        marks_this_layer = -(-(n_marks - placed) // remaining_layers)  # ceil split
        for i in range(marks_this_layer):
            row = i // cols
            y = cy - (marks_this_layer // (2 * cols) + 1) * spacing + row * spacing
            # serpentine: even rows go left->right, odd rows right->left
            ax, bx = (x_left, x_right) if row % 2 == 0 else (x_right, x_left)
            if not first:
                # guard the travel to this mark with a retraction / unretraction pair
                steps.append(fc.Retraction(distance=retraction_distance, speed=retraction_speed))
                steps.append(fc.Extruder(on=False))
                steps.append(fc.Point(x=ax, y=y, z=z + travel_lift))
                steps.append(fc.Point(x=ax, y=y, z=z))
                steps.append(fc.Extruder(on=True))
                steps.append(fc.Unretraction(distance=retraction_distance, speed=retraction_speed))
                travels += 1
            else:
                steps.append(fc.Point(x=ax, y=y, z=z))
            steps.append(fc.Point(x=bx, y=y, z=z))   # the extruded mark itself
            placed += 1
            first = False
            if placed >= n_marks:
                break

    assert travels == retractions, (travels, retractions)
    return steps
