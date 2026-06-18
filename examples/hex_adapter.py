"""Hex Adapter - a hexagonal honeycomb adapter ring printed as one continuous path.

A faithful reimplementation of the FullControl "Hex Adapter" demo: a single hexagonal cell built
from an inner hexagonal hole surrounded by six outer hexagon wall segments, so the part is a thick
hexagonal washer / adapter (an inner hex port inside an outer hex body). The whole cross-section is
traced as one continuous, seam-stitched toolpath and then stacked straight up for `height` mm, so it
prints as a hexagonal prism with no travel moves or retractions (the lattice "continuous print
path").

The cross-section is one `hex_unit` - a partial double wall running outer-vertex -> outer-edge
midpoint -> inner hexagon edge -> next outer-edge midpoint -> next outer-vertex - rotated into the
six 60 degrees sectors of the hexagon. Sizing follows the original model exactly: the inner and
outer "size" parameters are flat-to-flat hex widths (corrected for line width), converted to
centre-to-vertex circumradii via the 2/sqrt(3) factor, with oversize/undersize trims for fine fit.
"""
from math import tau

import fullcontrol as fc


def hex_adapter(inner_size: float = 10.0, outer_size: float = 16.0, height: float = 4.0,
                inner_oversize: float = 0.2, outer_undersize: float = 0.2,
                extrusion_width: float = 0.6, extrusion_height: float = 0.2,
                centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """Build a hexagonal honeycomb adapter ring as a continuous-path prism.

    inner_size: flat-to-flat width of the central hexagonal hole (mm).
    outer_size: flat-to-flat width of the outer hexagonal body (mm).
    height: thickness of the adapter (mm).
    inner_oversize: positive grows the hole (fine fit tweak, mm).
    outer_undersize: positive shrinks the outer body (fine fit tweak, mm).
    extrusion_width / extrusion_height: printed line width and layer height (mm).
    centre: (x, y) of the hexagon centre on the bed (mm).
    first_layer_gap: nozzle-to-bed gap for the first layer, as a fraction of a layer (mm).
    """
    cx, cy = centre
    eh = extrusion_height
    layers = max(1, int(round(height / eh)))

    # the size params are wall-to-wall; nudge by half a line so the printed faces land on size
    inner_ftf = inner_size + extrusion_width / 2
    outer_ftf = outer_size - extrusion_width / 2

    # flat-to-flat -> centre-to-vertex circumradius (regular hexagon), plus the fine-fit trims
    r_hex_inner = (inner_ftf / 2) * (2 / 3 ** 0.5) + inner_oversize
    r_hex_outer = (outer_ftf / 2) * (2 / 3 ** 0.5) - outer_undersize

    origin = fc.Point(x=0.0, y=0.0, z=0.0)
    hex_outer = fc.polygonXY(origin, r_hex_outer, tau / 2, 6, cw=False)
    hex_inner = fc.polygonXY(origin, r_hex_inner, tau / 2, 6, cw=False)

    # one 60 degrees segment of the continuous double-wall path
    hex_unit = [
        hex_outer[0],
        fc.midpoint(hex_outer[0], hex_outer[5]),
        hex_inner[0],
        hex_inner[1],
        fc.midpoint(hex_outer[1], hex_outer[2]),
        hex_outer[1],
    ]

    steps_one_layer = []
    for i in range(6):
        steps_one_layer += fc.move_polar(hex_unit, origin, 0, i * (tau / 6))

    steps_multilayer = fc.move(steps_one_layer, fc.Vector(z=eh), copy=True, copy_quantity=layers)

    steps = fc.move(steps_multilayer, fc.Vector(x=cx, y=cy, z=first_layer_gap * eh))
    return [fc.ExtrusionGeometry(width=extrusion_width, height=eh)] + steps


if __name__ == '__main__':
    steps = hex_adapter()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='hex_adapter',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.2}))
    print('wrote hex_adapter.gcode')
