"""Print with blobs instead of lines - a faithful take on FullControl's "Blob Printing" model.

Most toolpaths deposit material by *moving* the nozzle along a line. Blob printing does the
opposite: the nozzle parks at a site, oozes a controlled volume of material in place with
`fc.StationaryExtrusion(volume=..., speed=...)` to build a single blob, then travels (extruder
OFF) to the next site and repeats. The printed object is a *field of discrete blobs* rather than
continuous beads.

Inspecting the reference gcode (`blob-printing.gcode`) confirms the mechanism precisely: every
blob is a `G0 F8000 X.. Y..` travel followed by a bare `G1 F100 E<vol>` line with no XY change -
material extruded while stationary. The reference walks a tube outline, oozing one equal blob per
site; the blob *size* and the *overlap* between neighbouring blobs are the defining variables.

This design mirrors the three catalogue parameters - blob width, blob overlap and extrusion speed -
but makes the result distinct from a plain stud grid in two ways:

  - blob WIDTH varies across the field as a gradient (`blob_width` -> `blob_width_max`), so the
    blobs grow from one corner to the other and each blob oozes a different volume (a blob's volume
    is taken as that of a sphere of the blob's width, mirroring "Blob Width (mm)");
  - blobs can be STACKED into little towers (`blob_layers` > 1), each layer parked one
    `layer_height` higher, so the field becomes an array of blob columns.

Blob centre-to-centre `spacing` is derived from the (mean) blob width and the `blob_overlap`
percentage, exactly as the catalogue's "Blob Overlap (%)" implies: 0% overlap places blobs one
width apart, higher overlap packs them closer.
"""
from math import pi

import fullcontrol as fc


def _sphere_volume(diameter: float) -> float:
    """Volume (mm^3) of a spherical blob of the given diameter - mirrors 'Blob Width (mm)'."""
    return (4.0 / 3.0) * pi * (diameter / 2.0) ** 3


def blob_printing(rows: int = 5, cols: int = 5, blob_width: float = 1.6,
                  blob_width_max: float = None, blob_overlap: float = 33.0,
                  extrusion_speed: int = 100, blob_layers: int = 1,
                  layer_height: float = 0.3, centre=(100.0, 100.0)) -> list:
    """A field of stationary-extrusion blobs, sized by a gradient and optionally stacked.

    Faithful reimplementation of FullControl's "Blob Printing" model: instead of drawing lines,
    the nozzle parks at each site and oozes a set volume in place with `fc.StationaryExtrusion`,
    travelling with the extruder off between sites. The three catalogue parameters are mirrored as
    `blob_width`, `blob_overlap` and `extrusion_speed`.

    Args:
        rows, cols: number of blob sites down / across the field.
        blob_width: blob diameter (mm) at the near corner; a blob's volume is that of a sphere of
            this diameter. Mirrors the catalogue "Blob Width (mm)" slider (0.6-2, default 1.6).
        blob_width_max: blob diameter (mm) at the far corner. When None (default) every blob shares
            `blob_width`; when given, the width sweeps linearly across the field so blob volumes
            form a gradient. Set > `blob_width` for growing blobs.
        blob_overlap: percent overlap between neighbouring blobs (0-50), mirroring "Blob Overlap
            (%)". 0% => spacing of one blob width; higher => blobs packed closer together.
        extrusion_speed: feedrate for each stationary ooze (mm/min or mm^3/min), mirroring
            "Extrusion Speed".
        blob_layers: number of blobs stacked at each site (1 = flat field, >1 = blob towers). Each
            stacked blob is parked one `layer_height` higher than the last.
        layer_height: vertical step between stacked blobs and the z of the first blob layer.
        centre: (x, y) centre of the blob field on the bed.

    Returns a list of FullControl steps beginning with its own `fc.ExtrusionGeometry`.
    """
    if rows < 1 or cols < 1:
        raise ValueError('rows and cols must be >= 1')
    if blob_layers < 1:
        raise ValueError('blob_layers must be >= 1')

    cx, cy = centre
    w_near = blob_width
    w_far = blob_width if blob_width_max is None else blob_width_max

    # spacing from the (mean) blob width and overlap %, like the catalogue's "Blob Overlap (%)"
    mean_width = (w_near + w_far) / 2.0
    spacing = mean_width * (1.0 - blob_overlap / 100.0)

    # centre the field about `centre`
    x0 = cx - (cols - 1) * spacing / 2.0
    y0 = cy + (rows - 1) * spacing / 2.0  # row 0 at the top

    # the extrusion geometry is nominal (blobs carry their own volume via StationaryExtrusion);
    # set width/height from the blob so visualisation and area estimates are sensible
    steps = [fc.ExtrusionGeometry(width=mean_width, height=layer_height)]

    n_sites = max(rows * cols - 1, 1)
    site_index = 0
    for r in range(rows):
        for c in range(cols):
            x = x0 + c * spacing
            y = y0 - r * spacing
            # linear width gradient across the field (corner to corner)
            frac = site_index / n_sites
            width = w_near + (w_far - w_near) * frac
            volume = _sphere_volume(width)
            for layer in range(blob_layers):
                z = (layer + 1) * layer_height
                steps.append(fc.Extruder(on=False))           # travel to the site, no extrusion
                steps.append(fc.Point(x=x, y=y, z=z))
                steps.append(fc.StationaryExtrusion(volume=volume, speed=extrusion_speed))
            site_index += 1

    return steps


if __name__ == '__main__':
    steps = blob_printing(rows=5, cols=5, blob_width_max=2.0, blob_layers=2)
    n_blobs = sum(1 for s in steps if isinstance(s, fc.StationaryExtrusion))
    vols = sorted({round(s.volume, 6) for s in steps if isinstance(s, fc.StationaryExtrusion)})
    print(f"blob_printing: {len(steps)} steps, {n_blobs} blobs, {len(vols)} distinct blob volumes")
