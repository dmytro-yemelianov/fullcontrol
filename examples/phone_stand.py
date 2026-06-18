"""AnyAngle Phone Stand - a wavy lattice tube that cradles a phone at any angle.

This reimplements FullControl's "AnyAngle Phone Stand" (catalogue hash 4d0e78, "Lattice phone
stand to hold a phone in portrait and landscape modes"). The real model is a single continuous,
support-free bead printed in vase/spiral mode: a roughly square (~84x84mm) lattice tube ~30mm tall
whose wavy walls climb continuously in z. A phone leans into the corrugated walls and is gripped by
the lattice slots, so it can stand at *any* angle in either portrait or landscape - hence "AnyAngle".

What was recovered from the published g-code (/tmp/fcxyz/anyangle-phone-stand.gcode):
  * ~36k extruding points, bbox ~84 x 84 x 30 mm, centred at (69.5, 69.5).
  * TRUE continuous-Z spiral/vase mode: z rises ~0.1mm per move, ~300 levels, NO held layers and
    NO seam - one seamless bead from base to top.
  * The XY footprint is a rounded-square / wavy loop (radius oscillates ~35-42mm around the turn,
    with four corners), i.e. a corrugated square tube, NOT a single angled back panel.
  * The silhouette pinches slightly at mid-height (waist span ~79mm) and flares back to ~84mm at
    the base and rim - the "clamping" waist that grips the phone.

Faithful here: the defining function and proportions - a continuous-Z spiral-mode wavy *square*
lattice tube at the recovered bbox (~84x84x30), with a clamping waist and the catalogue's four
design params + the "Angry Mode" toggle mirrored as silhouette controls:
  * stand_height  <- "Stand Height (mm)"      (20-40, def 30)   -> tube height
  * stand_angle   <- "Stand Angles"           (9-19, def 13)    -> lean/slant of the wall waves
  * clamping      <- "Clamping Tightness (%)"  (0-100, def 50)   -> how hard the waist pinches in
  * wave_size     <- "Wave Size (%)"           (50-150, def 100) -> corrugation amplitude
  * angry_mode    <- "Angry Mode" checkbox     (off)             -> sharpens waves into spikes

Approximated (honest): the exact lattice/wave phase progression and the precise per-turn point
count are reconstructed parametrically rather than copied bead-for-bead; the real model's wall is a
phase-shifting corrugation lattice, here rendered as a sinusoidal (or, in Angry Mode, triangular)
corrugation whose phase drifts with height so successive turns interlock like the original lattice.
The result matches the original's bbox, square footprint, clamping waist and adjustable-angle essence.
"""
from math import tau, sin, asin, pi, cos

import fullcontrol as fc


def _rounded_square(angle: float, half: float, corner: float) -> float:
    """Radius of a rounded-square (superellipse-ish) outline at polar `angle`.

    half: half-width of the square (centre to flat). corner: 0 -> a circle, 1 -> a hard square.
    Uses the chamfered max-norm so corners sit at +-half*sqrt(2) and flats at +-half.
    """
    c, s = abs(cos(angle)), abs(sin(angle))
    chebyshev = max(c, s)            # square (max-norm): r*max(|cos|,|sin|) = half
    euclid = 1.0                     # circle
    blend = corner * chebyshev + (1.0 - corner) * euclid
    return half / blend


def phone_stand(stand_height: float = 30.0, stand_angle: float = 13.0, clamping: float = 50.0,
                wave_size: float = 100.0, angry_mode: bool = False, size: float = 84.0,
                layer_height: float = 0.1, segments_per_layer: int = 240,
                extrusion_width: float = 0.6, centre=(69.5, 69.5),
                first_layer_gap: float = 0.32) -> list:
    """Build the AnyAngle Phone Stand: a continuous-Z spiral-mode wavy square lattice tube.

    stand_height: tube height (mm); catalogue range 20-40, default 30.
    stand_angle: wall-wave lean angle (deg); catalogue 9-19, default 13. Larger = more slanted
        corrugations (the phone-supporting surface shifts more in XY as it climbs - the adjustable
        lean that lets a phone rest at a steeper angle).
    clamping: clamping tightness %, catalogue 0-100, default 50. Controls how far the silhouette
        pinches in at mid-height (the waist that grips the phone).
    wave_size: corrugation amplitude %, catalogue 50-150, default 100.
    angry_mode: if True, the sinusoidal corrugation becomes a sharp triangular zig-zag (spiky,
        "angry" silhouette) instead of smooth waves.
    size: footprint width across flats (mm); recovered ~84 from the real g-code.
    Returns a list starting with its own fc.ExtrusionGeometry, then the spiral bead Points.
    """
    cx, cy = centre
    eh = layer_height
    half = size / 2.0
    turns = max(1.0, stand_height / eh)
    total_segments = max(1, int(round(turns * segments_per_layer)))

    corner = 0.55                                   # rounded-square footprint (matches recovered shape)
    waves = 4                                        # corrugations per wall (~ the recovered lattice)
    # wall-wave lean: convert the catalogue "Stand Angle" (deg) into a phase drift per turn, so the
    # corrugation crest shifts around the loop as z climbs - the support surface leans with height.
    phase_drift_per_turn = tau * (stand_angle / 360.0)
    amp = half * 0.06 * (wave_size / 100.0)          # corrugation depth (~5% of half-width nominally)
    # clamping waist: pinch the mid-height radius in by up to ~6% of half-width at clamping=100.
    waist_depth = half * 0.06 * (clamping / 100.0)

    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=eh)]
    for i in range(total_segments + 1):
        frac = i / segments_per_layer                # turns completed
        angle = (frac * tau) % tau
        u = i / total_segments                        # 0..1 up the height
        z = frac * eh + first_layer_gap

        base_r = _rounded_square(angle, half, corner)

        # corrugation phase: `waves` per turn, plus a lean drift that grows with height
        phase = waves * angle + frac * phase_drift_per_turn
        if angry_mode:
            # triangular zig-zag: sharp spikes instead of smooth waves
            tri = 2.0 / pi * asin(sin(phase))
            corr = amp * tri
        else:
            corr = amp * sin(phase)

        # clamping waist: a single inward dip centred at mid-height (sin^2 bump, 0 at base/rim)
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
