"""2000-Retractions Test - a flat retraction calibration/stress test.

Reimplementation of FullControl's "2000-Retractions Test" demo (fullcontrol.xyz model `3bfcdb`,
"Test lots of retraction settings under lots of printing conditions"). The original prints a flat
single-layer field of short extruded marks and hops between them, performing a configurable - and
deliberately large - number of retractions in well under an hour, so you can dial in retraction
distance/speed against stringing.

Reverse-engineered from `2000-retractions-test.gcode` (986 extruding points, bbox ~178x146x0.2mm -
essentially flat / single layer): the toolpath is a bed-filling rectangular field of short straight
marks laid out on a regular grid (a dense array of columns x rows of short marks that nearly fills a
200mm bed), each travel between marks bracketed by a firmware retraction (`G10`) and an unretraction
(`G11`). This reimplementation does the same thing with explicit FullControl retraction steps: every
inter-mark travel is guarded by an `fc.Retraction` / `fc.Unretraction` pair (with the extruder lifted
and turned off across the hop), so the print performs exactly `retractions` retractions.

The design is parametric on the retraction count itself (`retractions`), plus the mark geometry
(`mark_length`, `spacing`), the retraction tuning under test (`retraction_distance`,
`retraction_speed`), and the flat-field knobs that mirror the original's sliders/checkboxes
(`layers`, `z_offset`, and the `fewer_*` shrink switches). `retraction_test()` returns a plain list
of FullControl steps starting with its own `fc.ExtrusionGeometry`, ready for any backend.
"""
import fullcontrol as fc


def retraction_test(retractions: int = 600, mark_length: float = 4.0, spacing: float = 6.0,
                    retraction_distance: float = 1.0, retraction_speed: float = 2000.0,
                    travel_lift: float = 0.6, cols: int | None = None, layers: int = 1,
                    z_offset: float = 0.0, layer_height: float = 0.2, extrusion_width: float = 0.4,
                    field_width: float = 178.0, field_height: float = 146.0,
                    centre=(100.0, 95.0), fewer_sets: bool = False, fewer_travel_lines: bool = False,
                    fewer_lines_per_set: bool = False) -> list:
    """A flat, bed-filling field of short extruded marks separated by retraction-guarded travels.

    The print lays down `retractions + 1` short vertical marks (so there are exactly `retractions`
    travels, each bracketed by an `fc.Retraction`/`fc.Unretraction` pair) over `layers` flat layers.
    Marks are arranged on a regular grid (columns x rows) that fills a `field_width` x `field_height`
    rectangle centred on the bed, exactly like the original retraction stress test which nearly fills
    a 200mm bed (~178x146mm).

    Args:
        retractions: target number of retractions to perform (== number of inter-mark travels). The
            real model targets ~2000; the default lays out a large bed-filling field.
        mark_length: length (mm) of each short extruded (vertical) mark.
        spacing: grid pitch (mm) used only as a fallback for a degenerate single-column or
            single-row field; otherwise the pitch is derived to fill `field_width` x `field_height`.
        retraction_distance: filament length (mm) to retract before each travel - the value under test.
        retraction_speed: retraction/unretraction feedrate (mm/min).
        travel_lift: z-hop (mm) applied across each travel to avoid dragging the nozzle.
        cols: marks per row; if None a roughly square field (matching the aspect ratio) is chosen.
        layers: number of (flat) layers - the field is repeated this many times up the z axis.
        z_offset: constant z shift (mm) added to every move (mirrors the model's Z Offset slider).
        layer_height: layer height (mm); also the first-layer gap above the bed.
        extrusion_width: extrusion width (mm).
        field_width: overall x extent (mm) of the bed-filling field.
        field_height: overall y extent (mm) of the bed-filling field.
        centre: (x, y) centre of the field on the bed.
        fewer_sets: shrink switch - halve the marks-per-row (fewer columns / sets).
        fewer_travel_lines: shrink switch - halve the number of rows (fewer travel lines).
        fewer_lines_per_set: shrink switch - halve `mark_length` (shorter marks).

    Returns:
        list: FullControl steps beginning with an `fc.ExtrusionGeometry`.
    """
    if retractions < 1:
        raise ValueError('retractions must be >= 1')

    if fewer_lines_per_set:
        mark_length = mark_length / 2.0

    n_marks = retractions + 1                       # N marks -> N-1 travels; per-layer count below
    cx, cy = centre

    # per-layer mark budget (spread the total field over the flat layers)
    per_layer = -(-n_marks // layers)               # ceil

    # choose a columns x rows grid for one layer matching the field aspect ratio
    aspect = field_width / field_height
    if cols is None:
        cols = max(1, round((per_layer * aspect) ** 0.5))
    if fewer_sets:
        cols = max(1, cols // 2)
    rows = max(1, -(-per_layer // cols))            # ceil so cols*rows >= per_layer
    if fewer_travel_lines:
        rows = max(1, rows // 2)

    # grid pitch fills the field exactly; for tiny fields fall back to `spacing`
    col_pitch = field_width / (cols - 1) if cols > 1 else spacing
    row_pitch = field_height / (rows - 1) if rows > 1 else spacing
    grid_w = col_pitch * (cols - 1)
    grid_h = row_pitch * (rows - 1)
    x0 = cx - grid_w / 2.0
    y0 = cy - grid_h / 2.0

    half = mark_length / 2.0

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=layer_height)]
    travels = 0                                     # retraction-guarded hops actually emitted
    placed = 0                                      # marks placed so far (across all layers)
    first = True

    for layer in range(layers):
        z = z_offset + layer_height + layer * layer_height
        idx = 0
        while idx < per_layer and placed < n_marks:
            row = idx // cols
            col = idx % cols
            # serpentine within a row to keep travels short
            c = col if row % 2 == 0 else (cols - 1 - col)
            x = x0 + c * col_pitch
            y_centre = y0 + row * row_pitch
            y_bottom = y_centre - half
            y_top = y_centre + half
            if not first:
                # guard the travel to this mark with a retraction / unretraction pair
                steps.append(fc.Retraction(distance=retraction_distance, speed=retraction_speed))
                steps.append(fc.Extruder(on=False))
                steps.append(fc.Point(x=x, y=y_bottom, z=z + travel_lift))
                steps.append(fc.Point(x=x, y=y_bottom, z=z))
                steps.append(fc.Extruder(on=True))
                steps.append(fc.Unretraction(distance=retraction_distance, speed=retraction_speed))
                travels += 1
            else:
                steps.append(fc.Point(x=x, y=y_bottom, z=z))
            steps.append(fc.Point(x=x, y=y_top, z=z))   # the extruded (vertical) mark itself
            placed += 1
            idx += 1
            first = False

    assert travels == retractions, (travels, retractions)
    return steps
