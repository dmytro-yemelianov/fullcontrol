"""The AnyAngle Phone Stand gallery design must resolve cleanly through all four backends and
exhibit its defining features as MEASURED from the published g-code: an OPEN, rounded-square,
corrugated C-wall cradle (~84x84x30mm) with a flat top edge and a fixed front opening - the cradle
a phone leans back into - NOT a closed box/tube. Mirrors tests/unit/test_examples.py's structure.
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
    # the smoke-test path the catalogue exercises: a short stand at coarse resolution
    return phone_stand(stand_height=6, segments_per_layer=60, centre=_CENTRE)


def _rad(p):
    cx, cy = _CENTRE
    return math.hypot(p.x - cx, p.y - cy)


def _ang(p):
    cx, cy = _CENTRE
    return math.degrees(math.atan2(p.y - cy, p.x - cx))


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


# ---- geometry: the defining features (measured from the real g-code) -----------------------------

def test_starts_with_its_own_extrusion_geometry():
    steps = phone_stand()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.6 and steps[0].height == 0.1


def test_continuous_z_bead_climbs_full_height():
    '''The bead climbs continuously from the first-layer gap up to the stand height (no z-zigzag).'''
    steps = phone_stand(stand_height=30)
    zs = [s.z for s in steps if isinstance(s, Point)]
    assert all(b >= a for a, b in zip(zs, zs[1:]))         # monotonic up
    assert zs[-1] - zs[0] > 29                              # climbs the full ~30mm
    rises = sum(1 for a, b in zip(zs, zs[1:]) if b > a + 1e-9)
    assert rises > 0.5 * len(zs)                            # most moves nudge z upward


def test_bbox_matches_the_real_model():
    'Recovered from the published g-code: a roughly square ~84x84mm footprint, ~30mm tall.'
    pts = [s for s in phone_stand(stand_height=30) if isinstance(s, Point)]
    xspan = max(p.x for p in pts) - min(p.x for p in pts)
    yspan = max(p.y for p in pts) - min(p.y for p in pts)
    zrange = max(p.z for p in pts) - min(p.z for p in pts)
    assert abs(xspan - yspan) < 6.0                        # near-square (portrait AND landscape)
    assert 78 < xspan < 92                                  # ~84mm across, like the real model
    assert 78 < yspan < 92
    assert 29 < zrange < 31                                 # ~30mm tall


def test_cross_section_is_an_open_cradle_not_a_closed_tube():
    '''THE crux: the real model is an OPEN C - every layer spans only ~231 deg with a ~129 deg front
    opening, not a full 360 deg loop. A closed box/tube would cover the whole circle.'''
    pts = [p for p in phone_stand(stand_height=10) if isinstance(p, Point)]
    angs = sorted(_ang(p) for p in pts)
    span = angs[-1] - angs[0]
    assert span < 300                                      # NOT a full 360 deg loop -> open
    assert span > 150                                      # but still a broad cradle arc
    # the open front is the angular sector NO point covers: the complement of [min, max] angle.
    open_mouth = 360 - span
    assert open_mouth > 60                                 # a wide open mouth (~129 deg in the real)
    # and that opening faces a consistent, fixed direction (does not rotate with height)
    top = [p for p in pts if p.z > max(q.z for q in pts) - 1]
    bot = [p for p in pts if p.z < min(q.z for q in pts) + 1]

    def gap_centre(group):
        a = sorted(_ang(p) for p in group)
        mid = ((a[0] + 360) + a[-1]) / 2
        return mid - 360 if mid > 180 else mid
    assert abs(gap_centre(top) - gap_centre(bot)) < 10     # fixed opening orientation (no twist)


def test_wider_stand_angle_opens_the_mouth_further():
    '''The catalogue "Stand Angle" widens the front opening so the phone can lean back further:
    a larger stand_angle -> a shorter wall arc -> a wider mouth.'''
    def arc_span(stand_angle):
        pts = [p for p in phone_stand(stand_height=6, stand_angle=stand_angle) if isinstance(p, Point)]
        a = sorted(_ang(p) for p in pts)
        return a[-1] - a[0]
    assert arc_span(9) > arc_span(13) > arc_span(19)       # bigger angle -> narrower wall -> wider mouth


def test_wall_top_edge_is_flat_not_a_height_scoop():
    '''Measured truth: the wall top edge is essentially FLAT (uniform height around the occupied
    arc) - the cradle "scoop" comes from the OPEN FRONT, not from a varying wall height. So within
    the occupied arc the max-z barely varies with angle.'''
    pts = [p for p in phone_stand(stand_height=30) if isinstance(p, Point)]
    bins = {}
    for p in pts:
        b = round(_ang(p) / 10) * 10                        # 10 deg angular bins over the arc
        bins[b] = max(bins.get(b, p.z), p.z)
    top_edge = list(bins.values())
    assert max(top_edge) - min(top_edge) < 1.0             # flat top: < 1mm variation across angles


def test_footprint_is_a_rounded_square_not_a_circle():
    'The cradle wall is square-ish: corners stick out noticeably further than the flats.'
    pts = [s for s in phone_stand(stand_height=4, wave_size=0) if isinstance(s, Point)]
    band = [p for p in pts if 1.0 <= p.z < 1.3]
    radii = [_rad(p) for p in band]
    assert max(radii) - min(radii) > 5.0                   # corner radius >> flat radius -> a square


def test_corrugated_lattice_walls():
    '''The walls are finely corrugated (the lattice waves). Isolate the pure wave by differencing
    against a wave-free wall: many corrugations ride around the arc, and deeper for bigger waves.'''
    waved = [p for p in phone_stand(stand_height=4, wave_size=150) if isinstance(p, Point)]
    flat = [p for p in phone_stand(stand_height=4, wave_size=0) if isinstance(p, Point)]
    seg = 240                                               # default segments_per_layer
    start = len(waved) // 2 - seg // 2                       # a turn near mid-height
    turn = [(_rad(a) - _rad(b)) for a, b in zip(waved[start:start + seg], flat[start:start + seg])]
    peaks = sum(1 for i in range(1, len(turn) - 1)
                if turn[i] > turn[i - 1] and turn[i] >= turn[i + 1] and turn[i] > 0.3)
    assert peaks > 8                                        # many fine corrugations around the arc

    def amp(ws):
        w = [p for p in phone_stand(stand_height=4, wave_size=ws) if isinstance(p, Point)]
        d = [_rad(a) - _rad(b) for a, b in zip(w, flat)]
        return max(d) - min(d)
    assert amp(150) > amp(50) + 0.5                        # bigger wave_size -> deeper corrugations


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

    # the triangular apex is a sharp corner; the smooth sine has lower curvature
    assert max_curvature(True) > 1.5 * max_curvature(False)
