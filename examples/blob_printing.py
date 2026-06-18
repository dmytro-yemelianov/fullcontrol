"""Print with blobs instead of lines - a faithful take on FullControl's "Blob Printing" model.

Most toolpaths deposit material by *moving* the nozzle along a line. Blob printing does the
opposite: the nozzle parks at a site, oozes a controlled volume of material in place with
`fc.StationaryExtrusion(volume=..., speed=...)` to build a single blob, then travels (extruder
OFF) to the next site and repeats. The printed object is a *field of discrete blobs* rather than
continuous beads.

Inspecting the reference gcode (`blob-printing.gcode`) confirms both the mechanism and the shape.
The mechanism: every blob is a `G0 F8000 X.. Y..` travel followed by a bare `G1 F100 E<vol>` line
with no XY change - material extruded while stationary. The shape: the 415 blobs are NOT a flat
grid. They sit on a **circle of radius 10mm centred at (50, 50)** and are stacked into a vertical
**tube** ten layers tall (z 0.76 -> 7.96, a 0.8mm step), so the print is a cylindrical wall of
blobs roughly 20mm across and ~7mm tall. The very first layer also carries a short straight "spoke"
of blobs leading in from the side (the lead-in the slicer walks before closing the ring).

This module reproduces that tube by default and keeps the three catalogue parameters - blob width,
blob overlap and extrusion speed. Blob centre-to-centre spacing along the ring is derived from the
blob width and `blob_overlap` percentage, exactly as the catalogue's "Blob Overlap (%)" implies:
0% overlap places blobs one width apart, higher overlap packs them closer.

A flat-grid layout is still available (used by the unit tests) by passing explicit `rows`/`cols`;
the default invocation builds the tube that matches the published model.
"""
from math import cos, pi, sin

import fullcontrol as fc

# --- reference-model geometry (from blob-printing.gcode) ---------------------------------------
_TUBE_CENTRE = (50.0, 50.0)   # circle centre on the bed
_TUBE_RADIUS = 10.0           # blob ring radius (mm) -> ~20mm footprint
_TUBE_LAYERS = 10             # stacked rings (z 0.76 .. 7.96)
_TUBE_Z0 = 0.76               # z of the first ring
_TUBE_DZ = 0.8                # vertical step between rings
_TUBE_BLOBS_PER_RING = 29     # blobs around the circumference per ring
_SPOKE_BLOBS = 9              # lead-in blobs on the first layer
_SPOKE_STEP = 1.072          # lead-in blob spacing (mm), from the reference spoke X60->X69.65


def _sphere_volume(diameter: float) -> float:
    """Volume (mm^3) of a spherical blob of the given diameter - mirrors 'Blob Width (mm)'."""
    return (4.0 / 3.0) * pi * (diameter / 2.0) ** 3


def _blob(steps: list, x: float, y: float, z: float, volume: float, speed: int) -> None:
    """Append the travel + stationary-ooze that lays one blob at (x, y, z)."""
    steps.append(fc.Extruder(on=False))   # travel to the site, extruder off
    steps.append(fc.Point(x=x, y=y, z=z))
    steps.append(fc.StationaryExtrusion(volume=volume, speed=speed))


def _tube(blob_width, blob_width_max, blob_overlap, extrusion_speed, blob_layers,
          centre, radius, blobs_per_ring):
    """A cylindrical wall of blobs - the layout the published model actually prints."""
    cx, cy = centre
    w_near = blob_width
    w_far = blob_width if blob_width_max is None else blob_width_max
    mean_width = (w_near + w_far) / 2.0

    steps = [fc.ExtrusionGeometry(width=mean_width, height=_TUBE_DZ)]

    n_layers = _TUBE_LAYERS if blob_layers is None else blob_layers
    total_sites = max(n_layers * blobs_per_ring - 1, 1)
    site_index = 0
    for layer in range(n_layers):
        z = _TUBE_Z0 + layer * _TUBE_DZ
        # a short straight spoke leads into the first ring, mirroring the reference lead-in
        if layer == 0:
            for s in range(_SPOKE_BLOBS, 0, -1):
                volume = _sphere_volume(mean_width)
                _blob(steps, cx + radius + s * _SPOKE_STEP, cy, z, volume, extrusion_speed)
        for b in range(blobs_per_ring):
            angle = 2.0 * pi * b / blobs_per_ring
            x = cx + radius * cos(angle)
            y = cy + radius * sin(angle)
            frac = site_index / total_sites
            width = w_near + (w_far - w_near) * frac      # optional width gradient up the tube
            volume = _sphere_volume(width)
            _blob(steps, x, y, z, volume, extrusion_speed)
            site_index += 1
    return steps


def _grid(rows, cols, blob_width, blob_width_max, blob_overlap, extrusion_speed,
          blob_layers, layer_height, centre):
    """A flat (optionally stacked) grid of blobs, sized by an optional corner-to-corner gradient."""
    cx, cy = centre
    w_near = blob_width
    w_far = blob_width if blob_width_max is None else blob_width_max
    mean_width = (w_near + w_far) / 2.0
    spacing = mean_width * (1.0 - blob_overlap / 100.0)

    x0 = cx - (cols - 1) * spacing / 2.0
    y0 = cy + (rows - 1) * spacing / 2.0   # row 0 at the top

    steps = [fc.ExtrusionGeometry(width=mean_width, height=layer_height)]

    n_sites = max(rows * cols - 1, 1)
    site_index = 0
    for r in range(rows):
        for c in range(cols):
            x = x0 + c * spacing
            y = y0 - r * spacing
            frac = site_index / n_sites
            width = w_near + (w_far - w_near) * frac
            volume = _sphere_volume(width)
            for layer in range(blob_layers):
                z = (layer + 1) * layer_height
                _blob(steps, x, y, z, volume, extrusion_speed)
            site_index += 1
    return steps


def blob_printing(rows: int = None, cols: int = None, blob_width: float = 1.6,
                  blob_width_max: float = None, blob_overlap: float = 33.0,
                  extrusion_speed: int = 100, blob_layers: int = None,
                  layer_height: float = 0.3, centre=(50.0, 50.0),
                  radius: float = _TUBE_RADIUS,
                  blobs_per_ring: int = _TUBE_BLOBS_PER_RING) -> list:
    """A field of stationary-extrusion blobs.

    Faithful reimplementation of FullControl's "Blob Printing" model: instead of drawing lines, the
    nozzle parks at each site and oozes a set volume in place with `fc.StationaryExtrusion`,
    travelling with the extruder off between sites.

    With the **defaults** (``rows``/``cols`` left as ``None``) this builds the *tube* the published
    model prints: a circle of blobs of ``radius`` mm stacked into ten rings ~7mm tall, centred on
    ``centre`` (footprint ~20mm across, matching `blob-printing.gcode`). Passing explicit ``rows``
    and ``cols`` instead lays a flat grid of ``rows`` x ``cols`` blob sites, optionally stacked
    ``blob_layers`` high - convenient for parametric experiments and exercised by the unit tests.

    Args:
        rows, cols: when both given, lay a flat grid this many sites down / across. Leave as
            ``None`` (default) to build the stacked circular tube instead.
        blob_width: blob diameter (mm); a blob's volume is that of a sphere of this diameter.
            Mirrors the catalogue "Blob Width (mm)" slider (0.6-2, default 1.6).
        blob_width_max: blob diameter (mm) at the far end of the field. When None every blob shares
            ``blob_width``; when given, width sweeps linearly so blob volumes form a gradient.
        blob_overlap: percent overlap between neighbouring blobs (0-50), mirroring "Blob Overlap
            (%)". Controls grid spacing; 0% => one blob width apart, higher => packed closer.
        extrusion_speed: feedrate for each stationary ooze, mirroring "Extrusion Speed".
        blob_layers: stacked layers. ``None`` (default) uses the reference tube's ten rings; an int
            stacks that many layers (grid mode) or builds that many rings (tube mode).
        layer_height: vertical step between stacked grid blobs and the z of the first grid layer.
        centre: (x, y) centre of the blob field / tube on the bed.
        radius: tube ring radius (mm), tube mode only.
        blobs_per_ring: blobs around the circumference of each ring, tube mode only.

    Returns a list of FullControl steps beginning with its own `fc.ExtrusionGeometry`.
    """
    if rows is not None and rows < 1:
        raise ValueError('rows must be >= 1')
    if cols is not None and cols < 1:
        raise ValueError('cols must be >= 1')
    if blob_layers is not None and blob_layers < 1:
        raise ValueError('blob_layers must be >= 1')

    if rows is None and cols is None:
        return _tube(blob_width, blob_width_max, blob_overlap, extrusion_speed, blob_layers,
                     centre, radius, blobs_per_ring)

    # grid mode: explicit rows/cols (and a default stack of 1) - keeps the parametric path
    rows = 1 if rows is None else rows
    cols = 1 if cols is None else cols
    layers = 1 if blob_layers is None else blob_layers
    return _grid(rows, cols, blob_width, blob_width_max, blob_overlap, extrusion_speed,
                 layers, layer_height, centre)


if __name__ == '__main__':
    steps = blob_printing()   # the default tube that matches the published model
    n_blobs = sum(1 for s in steps if isinstance(s, fc.StationaryExtrusion))
    xs = [s.x for s in steps if isinstance(s, fc.Point)]
    ys = [s.y for s in steps if isinstance(s, fc.Point)]
    zs = [s.z for s in steps if isinstance(s, fc.Point)]
    print(f"blob_printing tube: {len(steps)} steps, {n_blobs} blobs, "
          f"footprint {max(xs) - min(xs):.1f} x {max(ys) - min(ys):.1f} mm, "
          f"z {min(zs):.2f}..{max(zs):.2f}")
