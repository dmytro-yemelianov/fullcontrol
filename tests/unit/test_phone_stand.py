"""The AnyAngle Phone Stand gallery design must resolve cleanly through all four backends and
exhibit its defining features: a continuous-Z spiral-mode wavy *square* lattice tube whose
corrugated support surface leans with height (the adjustable angle) and that pinches in at a
clamping waist. Mirrors tests/unit/test_examples.py's structure for the gallery designs.
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.phone_stand import phone_stand

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

_CENTRE = (69.5, 69.5)


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small():
    # small-but-representative: a short stand at coarse resolution so the suite stays fast
    return phone_stand(stand_height=6, segments_per_layer=96, centre=_CENTRE)


def _rad(p):
    cx, cy = _CENTRE
    return math.hypot(p.x - cx, p.y - cy)


# ---- backend smoke / sanity (mirrors test_examples.py) -------------------------------------------

def test_design_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


def test_design_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


def test_design_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


# ---- geometry: the defining features -------------------------------------------------------------

def test_starts_with_its_own_extrusion_geometry():
    steps = phone_stand()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.6 and steps[0].height == 0.1


def test_continuous_z_spiral_mode_no_seam():
    '''The real model is a single seamless bead: z rises continuously (monotonic, no held layers,
    no z-zigzag) from the first-layer gap up to the stand height.'''
    steps = phone_stand(stand_height=30)
    zs = [s.z for s in steps if isinstance(s, Point)]
    assert all(b >= a for a, b in zip(zs, zs[1:]))         # monotonic up - continuous spiral
    assert zs[-1] - zs[0] > 29                              # climbs the full ~30mm
    # not a stack of held layers: almost every step nudges z upward (spiral, not flat layers)
    rises = sum(1 for a, b in zip(zs, zs[1:]) if b > a + 1e-9)
    assert rises > 0.5 * len(zs)


def test_bbox_matches_the_real_model():
    'Recovered from the published g-code: a roughly square ~84x84mm footprint, ~30mm tall.'
    pts = [s for s in phone_stand(stand_height=30) if isinstance(s, Point)]
    xspan = max(p.x for p in pts) - min(p.x for p in pts)
    yspan = max(p.y for p in pts) - min(p.y for p in pts)
    zrange = max(p.z for p in pts) - min(p.z for p in pts)
    assert abs(xspan - yspan) < 1.0                        # square footprint (portrait AND landscape)
    assert 78 < xspan < 92                                  # ~84mm across, like the real model
    assert 29 < zrange < 31                                 # ~30mm tall


def test_footprint_is_a_rounded_square_not_a_circle():
    'The lattice tube is square-ish: corners stick out noticeably further than the flats.'
    pts = [s for s in phone_stand(stand_height=4, wave_size=0) if isinstance(s, Point)]
    band = [p for p in pts if 1.0 <= p.z < 1.3]
    radii = [_rad(p) for p in band]
    assert max(radii) - min(radii) > 5.0                   # corner radius >> flat radius -> a square


def test_corrugated_lattice_walls():
    '''The walls are corrugated (the lattice waves). Isolate the pure wave by differencing against a
    wave-free stand: there are exactly four corrugations per turn.'''
    waved = [p for p in phone_stand(stand_height=4, wave_size=150) if isinstance(p, Point)]
    flat = [p for p in phone_stand(stand_height=4, wave_size=0) if isinstance(p, Point)]
    seg = 240                                               # default segments_per_layer
    start = len(waved) // 2 - seg // 2                       # a turn near mid-height
    turn = [(_rad(a) - _rad(b)) for a, b in zip(waved[start:start + seg], flat[start:start + seg])]
    peaks = sum(1 for i in range(1, len(turn) - 1)
                if turn[i] > turn[i - 1] and turn[i] >= turn[i + 1] and turn[i] > 0.5)
    assert peaks == 4                                       # four corrugated walls

    # bigger wave_size -> deeper corrugations
    def amp(ws):
        w = [p for p in phone_stand(stand_height=4, wave_size=ws) if isinstance(p, Point)]
        d = [_rad(a) - _rad(b) for a, b in zip(w, flat)]
        return max(d) - min(d)
    assert amp(150) > amp(50) + 0.5


def test_support_surface_leans_with_height_by_the_stand_angle():
    '''The defining "AnyAngle" feature: the corrugation crest (the surface a phone leans on) shifts
    in XY as it climbs, and the shift grows with `stand_angle`. Measured over a few turns (before
    the spiral phase wraps) on the +x wall sector, differenced against a wave-free stand.'''
    cx, cy = _CENTRE

    def crest_y(stand_angle, turn):
        waved = [p for p in phone_stand(stand_angle=stand_angle, wave_size=150, stand_height=2.0)
                 if isinstance(p, Point)]
        flat = [p for p in phone_stand(stand_angle=stand_angle, wave_size=0, stand_height=2.0)
                if isinstance(p, Point)]
        seg = 240
        w, f = waved[turn * seg:(turn + 1) * seg], flat[turn * seg:(turn + 1) * seg]
        cand = [(a.y, _rad(a) - _rad(b)) for a, b in zip(w, f) if a.x > cx and abs(a.y - cy) < 20]
        return max(cand, key=lambda v: v[1])[0]             # y of the crest in the +x wall sector

    def drift(stand_angle):
        return abs(crest_y(stand_angle, 3) - crest_y(stand_angle, 0))

    d_shallow, d_default, d_steep = drift(9), drift(13), drift(19)
    assert d_shallow > 0.5                                  # the surface genuinely leans (not rings)
    assert d_shallow < d_default < d_steep                  # steeper stand_angle -> more lean


def test_clamping_waist_grips_the_phone():
    '''Clamping tightness pinches the silhouette inward at mid-height (the waist that grips the
    phone): the base/rim are wider than the waist, and more clamping -> a tighter waist.'''
    def mid_radius(clamping):
        pts = [p for p in phone_stand(stand_height=30, clamping=clamping, wave_size=0)
               if isinstance(p, Point) and 14.5 <= p.z < 15.5]
        return sum(_rad(p) for p in pts) / len(pts)

    def base_radius(clamping):
        pts = [p for p in phone_stand(stand_height=30, clamping=clamping, wave_size=0)
               if isinstance(p, Point) and 0.5 <= p.z < 1.5]
        return sum(_rad(p) for p in pts) / len(pts)

    assert mid_radius(100) < base_radius(100) - 1.0         # waist clearly pinched in vs the base
    assert mid_radius(100) < mid_radius(0) - 1.0            # more clamping -> tighter waist
    assert abs(mid_radius(0) - base_radius(0)) < 0.5        # no clamping -> straight side (no waist)


def test_angry_mode_sharpens_the_waves():
    '''Angry Mode turns the smooth sinusoidal corrugation into a sharp triangular zig-zag. A
    triangle wave has a pointed apex (a corner) where a sine is rounded, so the wall profile's
    curvature (second difference of the pure-wave signal) spikes far higher in angry mode.'''
    flat = [p for p in phone_stand(stand_height=4, wave_size=0) if isinstance(p, Point)]

    def max_curvature(angry):
        w = [p for p in phone_stand(stand_height=4, wave_size=150, angry_mode=angry)
             if isinstance(p, Point)]
        dev = [_rad(a) - _rad(b) for a, b in zip(w, flat)]   # pure-wave signal (vs a wave-free wall)
        return max(abs(dev[i + 1] - 2 * dev[i] + dev[i - 1]) for i in range(1, len(dev) - 1))

    # the triangular apex is a sharp corner; the smooth sine has near-zero curvature everywhere
    assert max_curvature(True) > 5 * max_curvature(False)
