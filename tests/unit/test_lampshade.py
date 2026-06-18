"""The FullControl Lampshade: a mathematically defined parametric flaring ribbed vase-mode shade.

Mirrors tests/unit/test_examples.py: the design must resolve to a non-trivial g-code toolpath,
simulate to a real print (time/volume > 0) and validate without errors on a generous 200^3 build
volume. Geometry asserts prove it actually flares (rim radius != base radius, per the flare param)
and carries `ribs` angular ribs (counted as radial maxima on a mid layer).
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.lampshade import lampshade

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

# a small-but-representative shade so the suite stays fast
_SEG = 48


def _small(**kw):
    params = dict(height=4, segments_per_layer=_SEG, ribs=8, rib_depth=3.0,
                  internal_hole_radius=12.0, inner_frame_amplitude=10.0, centre_xy=60.0)
    params.update(kw)
    return lampshade(**params)


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def test_lampshade_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


def test_lampshade_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


def test_lampshade_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_lampshade_starts_with_its_own_extrusion_geometry():
    steps = _small()
    assert isinstance(steps[0], fc.ExtrusionGeometry)


def _radii(layer, c):
    return [math.hypot(p.x - c, p.y - c) for p in layer]


def test_lampshade_flares_from_base_to_rim():
    'The shade widens with height by inner_frame_amplitude (rim radius != base radius).'
    c, hole, amp = 60.0, 12.0, 14.0
    steps = lampshade(internal_hole_radius=hole, inner_frame_amplitude=amp, centre_xy=c,
                      height=6, segments_per_layer=_SEG, ribs=8, rib_depth=2.0, twist_turns=0.0)
    pts = [s for s in steps if isinstance(s, Point)]
    # rib crests sit on the smooth flare, so the max radius of a layer tracks the flare profile
    base_max = max(_radii(pts[:_SEG], c))
    rim_max = max(_radii(pts[-_SEG:], c))
    assert rim_max > base_max + amp * 0.7           # clearly flares outward
    assert abs(base_max - hole) < 0.5               # base crest ~ the internal hole radius
    assert abs(rim_max - (hole + amp)) < 0.5        # rim crest ~ hole + flare amplitude


def test_lampshade_carries_ribs_angular_ribs():
    'Count radial maxima around a mid layer: a `ribs`-fluted shade crests exactly `ribs` times.'
    c, ribs = 60.0, 9
    steps = lampshade(internal_hole_radius=12.0, inner_frame_amplitude=10.0, centre_xy=c,
                      height=4, segments_per_layer=240, ribs=ribs, rib_depth=4.0, twist_turns=0.0)
    pts = [s for s in steps if isinstance(s, Point)]
    # one full turn at mid height; count crests on the circular layer so the seam isn't double/under
    seg = 240
    start = (len(pts) // 2 // seg) * seg
    rs = _radii(pts[start:start + seg], c)           # exactly one turn (no repeated seam point)
    n = len(rs)
    crests = sum(1 for i in range(n) if rs[i] > rs[(i - 1) % n] and rs[i] >= rs[(i + 1) % n])
    assert crests == ribs                            # exactly `ribs` angular ribs


def test_lampshade_ribs_only_cut_inward():
    'Ribs remove material: every point sits at or inside the smooth flare (crest on it, troughs in).'
    c, hole, amp, depth = 60.0, 12.0, 12.0, 4.0
    steps = lampshade(internal_hole_radius=hole, inner_frame_amplitude=amp, centre_xy=c,
                      height=4, segments_per_layer=120, ribs=8, rib_depth=depth, twist_turns=0.0)
    H = 4.0
    for p in (s for s in steps if isinstance(s, Point)):
        f = min(1.0, (p.z - 0.8) / H)
        flare = hole + amp * f
        r = math.hypot(p.x - c, p.y - c)
        assert r <= flare + 1e-9                      # never bulges past the smooth flare
        assert r >= flare - depth - 1e-9              # never cuts deeper than rib_depth


def test_lampshade_twist_rotates_the_ribs_with_height():
    'A non-zero twist rotates the rib crests between the base and the top (helical flutes).'
    c, ribs = 60.0, 8
    steps = lampshade(internal_hole_radius=12.0, inner_frame_amplitude=10.0, centre_xy=c,
                      height=6, segments_per_layer=240, ribs=ribs, rib_depth=4.0, twist_turns=0.5)
    pts = [s for s in steps if isinstance(s, Point)]

    def crest_angle(layer):
        return max(layer, key=lambda p: math.hypot(p.x - c, p.y - c))
    p0 = crest_angle(pts[:240])
    p1 = crest_angle(pts[-240:])
    a0 = math.atan2(p0.y - c, p0.x - c)
    a1 = math.atan2(p1.y - c, p1.x - c)
    assert abs(a0 - a1) > 0.1                          # crest rotates with height -> helical ribs
