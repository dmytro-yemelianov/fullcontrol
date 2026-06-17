"""Gyroid infill block - ONE continuous bead approximating a gyroid TPMS inside a box.

A gyroid is a triply-periodic minimal surface; slicers normally print its infill as many
separate strokes joined by travels. FullControl can do something only a parametric toolpath can:
weave the whole thing as a single seamless bead with NO retractions and NO travel jumps.

The trick is the layer-by-layer weave. On each layer at height z we lay a serpentine of
sine waves; the wave PHASE advances with z (so the pattern shears as it rises) and the
serpentine DIRECTION alternates every layer - one layer's waves run along x, the next along y.
That interlocking of orthogonal, phase-shifted sine sheets is exactly what gives a gyroid its
woven look. Each layer's end is joined straight to the next layer's start, so the entire block
is one continuous toolpath.
"""
from math import tau, sin

import fullcontrol as fc


def gyroid_infill(size_x: float = 30.0, size_y: float = 30.0, height: float = 10.0,
                  cell_size: float = 6.0, layer_height: float = 0.3, resolution: int = 12,
                  amplitude: float = None, extrusion_width: float = 0.6, centre=(50.0, 50.0),
                  first_layer_gap: float = 0.8) -> list:
    """Build a continuous gyroid-infill toolpath inside a size_x by size_y by height block.

    size_x / size_y: footprint of the block (mm), centred on `centre`.
    height: total height (mm).
    cell_size: gyroid period (mm) - the wavelength of the sine weave in both plan and z.
    layer_height: z rise per layer (mm).
    resolution: polyline points per wavelength (higher = smoother waves).
    amplitude: peak wave deviation (mm) of each pass from its straight track. Defaults to a
        fifth of cell_size, which gives well-formed interlocking lobes whose total wiggle stays
        below the sweep length, so each layer keeps a clear, well-defined sweep direction.
    extrusion_width / first_layer_gap / centre: print setup.
    """
    cx, cy = centre
    eh = layer_height
    amp = amplitude if amplitude is not None else cell_size / 5.0
    half_x, half_y = size_x / 2.0, size_y / 2.0
    x0, x1 = cx - half_x, cx + half_x
    y0, y1 = cy - half_y, cy + half_y

    n_layers = max(1, int(round(height / eh)))
    # number of parallel passes across the block, one per gyroid half-period
    passes_x = max(1, int(round(size_x / cell_size)))   # tracks spaced across x (for y-waving layers)
    passes_y = max(1, int(round(size_y / cell_size)))   # tracks spaced across y (for x-waving layers)

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]

    for layer in range(n_layers):
        z = first_layer_gap + layer * eh
        phase = (layer * eh) / cell_size * tau          # wave phase shears with height
        x_waving = (layer % 2 == 0)                      # alternate weave direction per layer

        if x_waving:
            # tracks run along x at evenly spaced y; each track waves in y
            n_tracks = passes_y
            for t in range(n_tracks):
                ty = y0 + (y1 - y0) * (t / n_tracks if n_tracks > 1 else 0.5)
                forward = (t % 2 == 0)                   # serpentine: alternate sweep direction
                n_pts = max(2, int(round(size_x / cell_size * resolution)))
                for i in range(n_pts + 1):
                    f = i / n_pts
                    x = x0 + (x1 - x0) * (f if forward else 1.0 - f)
                    wave = amp * sin((x - x0) / cell_size * tau + phase)
                    y = min(y1, max(y0, ty + wave))
                    steps.append(fc.Point(x=x, y=y, z=z))
        else:
            # tracks run along y at evenly spaced x; each track waves in x
            n_tracks = passes_x
            for t in range(n_tracks):
                tx = x0 + (x1 - x0) * (t / n_tracks if n_tracks > 1 else 0.5)
                forward = (t % 2 == 0)
                n_pts = max(2, int(round(size_y / cell_size * resolution)))
                for i in range(n_pts + 1):
                    f = i / n_pts
                    y = y0 + (y1 - y0) * (f if forward else 1.0 - f)
                    wave = amp * sin((y - y0) / cell_size * tau + phase)
                    x = min(x1, max(x0, tx + wave))
                    steps.append(fc.Point(x=x, y=y, z=z))

    return steps


if __name__ == '__main__':
    steps = gyroid_infill()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='gyroid_infill',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote gyroid_infill.gcode')
