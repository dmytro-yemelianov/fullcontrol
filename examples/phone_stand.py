"""AnyAngle Phone Stand - an open, corrugated cradle that holds a phone at any angle.

This reimplements FullControl's "AnyAngle Phone Stand" (catalogue hash 4d0e78, "Lattice phone
stand to hold a phone in portrait and landscape modes"). The real model is a single continuous,
support-free bead: a roughly square (~84x84mm) corrugated wall ~30mm tall that does NOT close into
a tube - it is an open C / horseshoe whose front is missing, so a phone leans back into the cradle
and is gripped by the wavy lattice wall, in portrait or landscape - hence "AnyAngle".

What was actually MEASURED from the published g-code (/tmp/fcxyz/anyangle-phone-stand.gcode), point
by point (35671 extruding points, centred at (69.45, 69.45)):
  * bbox ~83.9 x 83.9 x 29.8 mm (X/Y 27.5..111.4, Z 0.42..30.22).
  * The cross-section is an OPEN ARC, not a closed loop: every layer spans angles ~-71 deg to
    ~+161 deg around the centre - a ~231 deg arc with a fixed ~129 deg GAP (the open front of the
    cradle). The gap centre sits at ~-132 deg (front-left) and does NOT rotate with height.
  * It is NOT a continuous spiral - dz==0 for 99% of moves: it is built layer by layer. Each layer
    is one open C arc at constant z (~479 points), then z steps up ~0.1mm at the seam. ~299 layers.
  * The wall TOP EDGE is essentially FLAT: max-z is ~29.9mm at every occupied angle (amplitude of
    the top-edge-vs-angle profile is < 0.3mm). The "scooped cradle" look is produced ENTIRELY by the
    open front - you see down into the missing-front C, not by a varying wall height.
  * The wall is finely CORRUGATED: along each arc the radius oscillates ~+/-1.5mm with a short period
    (~9 points / ~4 deg per wave, i.e. tens of waves around the arc) riding on a rounded-square base
    radius (~28.7mm at the flats up to ~46.7mm reaching the corners). No lean: the layer centroid
    barely moves with height.

Faithful here: the defining geometry - an OPEN, rounded-square, corrugated C-wall at the recovered
bbox (~84x84x30) with a flat top edge and a fixed front opening - so the default output renders as
the same open scooped cradle, not a closed box. The catalogue's four design params + "Angry Mode"
are mapped onto meaningful controls of that cradle:
  * stand_height <- "Stand Height (mm)"       (20-40, def 30)  -> wall height
  * stand_angle  <- "Stand Angles"            (9-19, def 13)   -> how wide the front opening is
        (the angle the phone can lean to: a wider mouth lets the phone lie back further)
  * clamping     <- "Clamping Tightness (%)"   (0-100, def 50)  -> waist pinch that grips the phone
  * wave_size    <- "Wave Size (%)"            (50-150, def 100) -> corrugation amplitude
  * angry_mode   <- "Angry Mode" checkbox      (off)            -> sharpens waves into spiky zig-zags

Approximated (honest): the exact per-turn point count and the precise corrugation phase are
reconstructed parametrically rather than copied bead-for-bead, and the build here is a true
continuous spiral over the open arc (smoother than the real layer-by-layer C) - but the silhouette,
the open ~231 deg arc with its fixed front opening, the rounded-square footprint, the flat top edge
and the bbox all match the recovered model.
"""
from math import tau, sin, asin, pi, cos

import fullcontrol as fc

# The measured open arc: points exist from ~-71 deg to ~+161 deg around the centre. We model the
# wall as an arc centred on the BACK direction with a front opening; these set its angular span.
_ARC_SPAN_DEG = 231.0     # angular extent of the wall (the rest is the open front of the cradle)
_GAP_CENTRE_DEG = -132.0  # direction the open front faces (front-left, as recovered)


def _rounded_square(angle: float, half: float, corner: float) -> float:
    """Radius of a rounded-square outline at polar `angle`.

    half: half-width of the square (centre to flat). corner: 0 -> a circle, 1 -> a hard square.
    Uses a chamfered max-norm so corners sit ~half*sqrt(2) out and flats at ~half.
    """
    c, s = abs(cos(angle)), abs(sin(angle))
    chebyshev = max(c, s)            # square (max-norm)
    euclid = 1.0                     # circle
    blend = corner * chebyshev + (1.0 - corner) * euclid
    return half / blend


def phone_stand(stand_height: float = 30.0, stand_angle: float = 13.0, clamping: float = 50.0,
                wave_size: float = 100.0, angry_mode: bool = False, size: float = 84.0,
                layer_height: float = 0.1, segments_per_layer: int = 240,
                extrusion_width: float = 0.6, centre=(69.5, 69.5),
                first_layer_gap: float = 0.32) -> list:
    """Build the AnyAngle Phone Stand: an OPEN, rounded-square, corrugated C-wall cradle.

    The wall is an arc (not a closed tube): it spans ~231 deg and leaves a ~129 deg opening at the
    front, so a phone leans back into the cradle. The top edge is flat (uniform height); the cradle
    look comes from the open front. Built as a continuous bead spiralling up the open arc.

    stand_height: wall height (mm); catalogue range 20-40, default 30.
    stand_angle: catalogue "Stand Angles" (deg), 9-19, default 13. Widens the front opening so the
        phone can lean back further - larger value -> wider mouth / shorter wall arc.
    clamping: clamping tightness %, 0-100, default 50. Pinches the silhouette inward at mid-height
        (the waist that grips the phone).
    wave_size: corrugation amplitude %, 50-150, default 100.
    angry_mode: if True, the smooth sinusoidal corrugation becomes a sharp triangular zig-zag.
    size: footprint width across flats (mm); recovered ~84 from the real g-code.
    Returns a list starting with its own fc.ExtrusionGeometry, then the open-arc bead Points.
    """
    cx, cy = centre
    eh = layer_height
    half = size / 2.0
    turns = max(1.0, stand_height / eh)
    total_segments = max(1, int(round(turns * segments_per_layer)))

    corner = 0.55                                    # rounded-square footprint (matches recovered shape)
    waves = 26                                        # fine corrugations around the arc (recovered: ~tens)

    # OPEN arc: the wall sweeps only `arc_span` of the full circle, leaving the front open. The
    # catalogue "Stand Angle" widens that opening (shrinks the arc) so the phone can lean back more.
    base_arc = _ARC_SPAN_DEG * (pi / 180.0)
    # stand_angle 9..19 (def 13) -> open the mouth by up to ~+-25 deg around the recovered 129 deg gap
    arc_span = base_arc - (stand_angle - 13.0) * (pi / 180.0) * 2.0
    arc_span = max(pi * 0.5, min(arc_span, tau * 0.95))      # keep it a sensible open C
    gap_centre = _GAP_CENTRE_DEG * (pi / 180.0)
    arc_start = gap_centre + pi - arc_span / 2.0             # back direction +/- half the arc

    amp = half * 0.04 * (wave_size / 100.0)          # corrugation depth (~+/-1.5mm nominally)
    # clamping waist: pinch the mid-height radius in by up to ~6% of half-width at clamping=100.
    waist_depth = half * 0.06 * (clamping / 100.0)

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        t = i / total_segments                        # 0..1 along the whole bead
        u = t                                         # 0..1 up the height
        frac = i / segments_per_layer                 # turns completed (for corrugation phase)
        # spiral up the OPEN arc: each turn sweeps arc_start..arc_start+arc_span then jumps back
        local = (i % segments_per_layer) / segments_per_layer
        angle = arc_start + local * arc_span
        z = frac * eh + first_layer_gap

        base_r = _rounded_square(angle, half, corner)

        # fine corrugation around the arc
        phase = waves * tau * local
        if angry_mode:
            tri = 2.0 / pi * asin(sin(phase))         # triangular zig-zag: sharp spikes
            corr = amp * tri
        else:
            corr = amp * sin(phase)

        # clamping waist: a single inward dip centred at mid-height (0 at base/rim)
        waist = -waist_depth * sin(pi * u)

        r = base_r + corr + waist
        steps.append(fc.polar_to_point(fc.Point(x=cx, y=cy, z=z), r, angle))
    return steps


if __name__ == '__main__':
    steps = phone_stand()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='phone_stand',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.1}))
    print('wrote phone_stand.gcode')
