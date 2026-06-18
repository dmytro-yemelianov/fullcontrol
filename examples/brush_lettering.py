"""A flat single-layer plaque whose bead swells and thins like a calligraphy brush stroke.

A normal slicer prints every line at one fixed width. FullControl can change the live extrusion
width per segment by emitting a fresh `fc.ExtrusionGeometry(width=...)` step mid-path - so a single
continuous bead can be fat where a pen-stroke presses down and a hairline where it lifts away. This
design traces a parametric stroke ('sine' | 'loop' | 'signature', or your own callable) across a flat
plaque and modulates the bead width along it, giving true calligraphic line weight: impossible on a
conventional slicer.

The width law follows the *downstroke* convention of broad-pen calligraphy - the bead is widest
where the stroke travels downward (the slow, weight-bearing part of a letter) and thinnest on the
upstroke - via the default `width_fn`. Pass any `width_fn(t) -> [0, 1]` (t the 0..1 path fraction)
to design your own weight profile.

    import fullcontrol as fc
    from examples import brush_lettering          # (exported only if registered)
    steps = brush_lettering(stroke='signature')
    gcode = fc.transform(steps, 'gcode', fc.GcodeControls(printer_name='generic',
                         initialization_data={'nozzle_temp': 210}))
"""
from math import tau, sin, cos

import fullcontrol as fc


def _stroke_sine(t: float) -> tuple:
    'A simple oscillating ribbon: marches in x, waves in y. Returns (x, y) in [0,1]x[-1,1].'
    return t, sin(t * tau * 2)


def _stroke_loop(t: float) -> tuple:
    'A looping flourish (a leaning figure-of-eight / lemniscate-ish curl).'
    a = t * tau
    return 0.5 * (1 + sin(a)), sin(2 * a)


def _stroke_signature(t: float) -> tuple:
    'A signature-like cursive ribbon: a rising baseline carrying three descending loops.'
    a = t * tau
    x = t
    y = 0.55 * sin(a * 3) - 0.25 * cos(a) + 0.20 * t
    return x, y


_STROKES = {'sine': _stroke_sine, 'loop': _stroke_loop, 'signature': _stroke_signature}


def _downstroke_weight(t: float, stroke, dt: float = 1e-3) -> float:
    '''Broad-pen weight law in [0,1]: fat on the downstroke, hairline on the upstroke.

    Estimates dy/dt of the stroke at t; maps a downward-moving pen (dy/dt < 0) to ~1 (full width)
    and an upward-moving pen to ~0 (hairline), with a smooth transition through the horizontals.
    '''
    t0 = min(max(t - dt, 0.0), 1.0)
    t1 = min(max(t + dt, 0.0), 1.0)
    _, y0 = stroke(t0)
    _, y1 = stroke(t1)
    span = max(t1 - t0, 1e-9)
    dy = (y1 - y0) / span
    # squash dy to [0,1] via a smooth sigmoid-like map; negative dy (down) -> wide, positive -> thin
    return 0.5 * (1.0 - dy / (abs(dy) + 1.0))


def brush_lettering(stroke='signature', width_fn=None, min_width: float = 0.4,
                    max_width: float = 1.4, length: float = 80.0, height_amplitude: float = 22.0,
                    layer_height: float = 0.3, segments: int = 240, centre=(100.0, 100.0),
                    first_layer_gap: float = 0.8) -> list:
    """Build a single-layer calligraphic bead with per-segment varying extrusion width.

    stroke: a preset name ('sine' | 'loop' | 'signature') or a callable t->(x, y) with t in [0,1]
        and x, y roughly in [0,1] and [-1,1] respectively (they are scaled by length/height).
    width_fn: a callable t->[0,1] mapping path fraction to a 0..1 weight, linearly remapped onto
        [min_width, max_width]. None uses the broad-pen downstroke law (fat going down).
    min_width / max_width: the hairline and the fattest bead width (mm).
    length: span of the plaque along x (mm); height_amplitude: vertical reach of the stroke (mm).
    layer_height: single-layer bead height (mm). segments: bead resolution.
    centre / first_layer_gap: print placement on the bed.
    """
    if isinstance(stroke, str):
        if stroke not in _STROKES:
            raise ValueError(f"unknown stroke {stroke!r}; choose from {sorted(_STROKES)} or pass a callable")
        stroke_fn = _STROKES[stroke]
    elif callable(stroke):
        stroke_fn = stroke
    else:
        raise TypeError('stroke must be a preset name or a callable t->(x, y)')

    if width_fn is None:
        def width_fn(t, _s=stroke_fn):
            return _downstroke_weight(t, _s)
    elif not callable(width_fn):
        raise TypeError('width_fn must be a callable t->[0,1]')

    if max_width < min_width:
        raise ValueError('max_width must be >= min_width')

    cx, cy = centre
    eh = layer_height
    z = first_layer_gap

    def width_at(t: float) -> float:
        w = width_fn(t)
        w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)   # clamp to [0,1]
        # quantise so the design emits a tidy, finite set of distinct widths (no float dithering)
        w = round(w, 3)
        return round(min_width + w * (max_width - min_width), 4)

    # Start with the design's own ExtrusionGeometry (rectangle area model so width*height -> area).
    steps = [fc.ExtrusionGeometry(area_model='rectangle', width=width_at(0.0), height=eh)]
    last_width = None
    for i in range(segments + 1):
        t = i / segments
        sx, sy = stroke_fn(t)
        x = cx - 0.5 * length + sx * length
        y = cy + sy * height_amplitude
        w = width_at(t)
        if w != last_width:                                # only emit a fresh width when it changes
            steps.append(fc.ExtrusionGeometry(width=w))
            last_width = w
        steps.append(fc.Point(x=x, y=y, z=z))
    return steps


if __name__ == '__main__':
    steps = brush_lettering()
    widths = {s.width for s in steps if isinstance(s, fc.ExtrusionGeometry)}
    print(f'{len(widths)} distinct widths, {min(widths):.2f}..{max(widths):.2f} mm')
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='brush_lettering',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote brush_lettering.gcode')
