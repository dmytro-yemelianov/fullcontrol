"""Tape-Reinforcement Research Demo - a flat coupon that pauses for tape to be embedded.

A reimplementation of the fullcontrol.xyz "Tape-Reinforcement Research Demo" (the design behind
tinyurl.com/3Dtape, where physio tape is reinforced with printed TPU and embedded between layers).
The idea is a research workflow, not a finished part: print a flat rectangular test specimen (a
long tensile-coupon strip), PAUSE the printer mid-print so a strip of reinforcing tape / fibre can
be laid down by hand onto the part, then carry on printing to embed it between the layers.

The original sliced g-code prints a flat strip whose footprint is ~44 mm wide (x) by ~154 mm long
(y) in a few layers and pauses (the real file does it with a `G4` dwell while the head parks high;
this reimplementation uses an explicit `fc.ManualGcode` pause command - `M0` by default - which is
the more usual "wait for the operator" instruction). The catalogue calls these the Tape Length
(150, the long axis = y) and Tape Width (40, the short axis = x), with Layers defaulting to 2. Each
layer is a solid raster (boustrophedon) fill of the rectangle, and a pause is emitted in the gap
*before* each layer listed in `tape_layers`, so the number of pauses in the g-code is exactly
`len(tape_layers)` - the parametric heart of the demo.
"""
import fullcontrol as fc


def tape_reinforcement(length: float = 150.0, width: float = 40.0, layers: int = 2,
                       tape_layers=(2,), pause_gcode: str = 'M0', infill: float = 0.5,
                       layer_height: float = 0.2, origin=(30.0, 30.0)) -> list:
    """Build a flat strip specimen that pauses between layers for reinforcing tape to be laid.

    length / width: footprint of the strip (mm) - a long flat rectangle (default 150 x 40, the
        catalogue's Tape Length / Tape Width). `length` is the LONG axis and runs along y; `width`
        is the short axis across x - matching the real long-narrow tensile coupon (~44 wide x ~154
        long).
    layers: number of solid raster layers in the specimen (>= 1; catalogue default 2).
    tape_layers: 1-based layer indices BEFORE which a pause is inserted, so the operator can lay
        tape onto the surface printed so far. The g-code therefore contains exactly
        len(tape_layers) pause commands. Values are clamped to 1..layers and de-duplicated.
    pause_gcode: the raw pause instruction emitted via fc.ManualGcode (e.g. 'M0' / 'M600' / 'M0 ;
        place tape'). This is the manual-intervention command the printer halts on.
    infill: extrusion width (mm) of each raster line; raster lines are spaced by this pitch across
        the strip so each layer prints out as a solid raster fill.
    layer_height: z rise per layer (mm) - also the extrusion height.
    origin: (x, y) of the strip's near-left corner on the bed.
    """
    layers = max(1, int(layers))
    ew = infill
    eh = layer_height
    x0, y0 = origin
    y1 = y0 + length                                         # length is the LONG axis, along y

    # which layer-gaps get a pause: 1-based, clamped into range, unique, in order
    pause_before = sorted({int(t) for t in tape_layers if 1 <= int(t) <= layers})

    # parallel raster lines run along y (the long axis), stacked across the width in x
    n_lines = max(2, int(round(width / ew)) + 1)
    xs = [x0 + (width * i / (n_lines - 1)) for i in range(n_lines)]

    steps = [fc.ExtrusionGeometry(width=ew, height=eh)]

    for layer in range(layers):                              # 0-based loop index
        if (layer + 1) in pause_before:                      # pause in the gap before this layer
            steps.append(fc.ManualGcode(text=f'{pause_gcode} ; pause - lay reinforcing tape'))
        z = eh + layer * eh                                  # first layer sits one layer-height up

        # alternate the long-axis sweep direction every other layer so the raster cross-hatches and
        # the layers bond (a solid coupon, not stacked unidirectional lines)
        flip = (layer % 2 == 1)
        line_order = list(range(n_lines))
        for li, line in enumerate(line_order):
            x = xs[line]
            # boustrophedon: each successive raster line reverses along y (one continuous path)
            forward = (li % 2 == 0)
            if flip:
                forward = not forward
            ya, yb = (y0, y1) if forward else (y1, y0)
            steps.append(fc.Point(x=x, y=ya, z=z))
            steps.append(fc.Point(x=x, y=yb, z=z))

    return steps


if __name__ == '__main__':
    steps = tape_reinforcement()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='tape_reinforcement',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'build_volume_y': 300}))
    print('wrote tape_reinforcement.gcode')
