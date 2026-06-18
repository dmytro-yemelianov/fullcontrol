"""The Pin-Support Challenge gallery design: a tall slender support-free pin capped with a wide cone.

Mirrors tests/unit/test_examples.py: the design must resolve to gcode (non-trivial), simulate
(time/volume > 0) and validate (no errors) on a generous build volume; plus geometry asserts that
prove the defining feature - it is tall and slender (height >> footprint radius), with conical_start
toggling between a tapered base and a flat-disc base.
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.pin_support_challenge import pin_support_challenge

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data=dict(_BUILD))


def _small():
    # small-but-representative: a short pin and small cone keep the suite fast
    return pin_support_challenge(height=6, cone_radius=3, base_radius=2, segments_per_layer=32)


def _radius(p, centre=(50, 50)):
    return math.hypot(p.x - centre[0], p.y - centre[1])


def test_resolves_to_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20           # a real toolpath, not a stub
    assert 'G1' in gcode                    # extruding moves were emitted


def test_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0            # material is actually deposited
    assert r.extruding_distance > 0


def test_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_starts_with_its_own_extrusion_geometry():
    steps = pin_support_challenge()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.4            # set by nozzle_size default


def test_pin_is_tall_and_slender():
    'The defining feature: a pin much taller than the footprint is wide, climbing straight up.'
    steps = pin_support_challenge(height=20, pillar_diameter=1.2, base_radius=5, cone_radius=10,
                                  conical_start=False)
    pts = [s for s in steps if isinstance(s, Point)]
    z_total = max(p.z for p in pts) - min(p.z for p in pts)
    footprint_radius = max(_radius(p) for p in pts)
    assert z_total > 25                                  # tall (pin + cone ~ 30 mm)
    assert footprint_radius < 11                         # narrow footprint (~10 mm radius cone rim)
    assert z_total > 2 * footprint_radius                # height >> footprint radius: slender

    # the pin itself is a single vertical bead on the axis, taller than it is wide
    axis_pts = [p for p in pts if _radius(p) < 1e-6]
    pin_rise = max(p.z for p in axis_pts) - min(p.z for p in axis_pts)
    assert pin_rise >= 20                                # the 20 mm pin climbs the full height
    assert pin_rise > 10 * 1.2                           # far taller than the pillar diameter


def test_conical_start_tapers_the_base_but_flat_does_not():
    'conical_start=True lifts the base into a tapered cone; False keeps it a flat disc.'
    common = dict(height=10, base_radius=5, cone_radius=4, segments_per_layer=48)
    flat = pin_support_challenge(conical_start=False, **common)
    coni = pin_support_challenge(conical_start=True, **common)

    def base_pts(steps):
        # the base is the leading spiral, before the pin climbs (identify it by low z)
        pts = [s for s in steps if isinstance(s, Point)]
        z_floor = min(p.z for p in pts)
        return pts, z_floor

    flat_pts, flat_floor = base_pts(flat)
    coni_pts, coni_floor = base_pts(coni)

    # flat base: the outer base ring sits at the same z as the centre apex (no taper)
    flat_base = [p for p in flat_pts if _radius(p) > 0.5 and p.z < flat_floor + 0.5]
    flat_base_z_spread = max(p.z for p in flat_base) - min(p.z for p in flat_base)
    assert flat_base_z_spread < 1e-6                     # flat disc: all base z equal

    # conical base: the outer ring is LOWER than the apex where the pin starts -> a tapered cone
    coni_base = [p for p in coni_pts if _radius(p) > 0.5]
    coni_base_z_spread = max(p.z for p in coni_base) - min(p.z for p in coni_base)
    assert coni_base_z_spread > 2.0                      # the base rises ~base_radius (5 mm) to apex


def test_cone_on_top_is_a_45_degree_cone():
    'The top cap opens out from the pin tip as a 45-degree cone (dr/dz = 1.0, the real model).'
    steps = pin_support_challenge(height=12, cone_radius=8, base_radius=3, segments_per_layer=64)
    pts = [s for s in steps if isinstance(s, Point)]
    z_top = max(p.z for p in pts)
    # the cone is the widest part, at the very top
    rim = [p for p in pts if p.z > z_top - 0.3]
    assert max(_radius(p) for p in rim) > 7.5            # opens to ~cone_radius at the rim
    # dr/dz ~ 1: the rim radius (~8) equals the cone's vertical rise (~8)
    cone_pts = [p for p in pts if p.z > z_top - 8.5]
    cone_rise = max(p.z for p in cone_pts) - min(p.z for p in cone_pts)
    assert abs(cone_rise - max(_radius(p) for p in rim)) < 1.0
