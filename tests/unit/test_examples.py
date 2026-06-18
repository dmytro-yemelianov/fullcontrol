"""Every gallery design (examples/) must resolve cleanly through all four backends.

These are smoke + sanity tests: each design is generated at a small size and run to gcode,
simulation and validation. They guard the example designs against API drift in the library and
prove the designs are real, printable toolpaths (non-trivial length, material deposited, in-bounds,
no validation errors against a generous build volume).
"""
import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples import (GALLERY, spiral_vase, ripple_vase, nonplanar_spacer, wave_bowl,
                      twisted_polygon_vase, helical_screw, textured_cone, revolve, mobius_band,
                      trefoil_tube, towers_grid, optimization_report, snake_soapdish,
                      hex_adapter, lampshade, nuts_and_bolts, star_polygon_lattice,
                      phone_stand, pin_support_challenge, overhang_challenge,
                      arc_vase, brush_lettering, bead_studs, retraction_test, blob_printing,
                      freeform_frosting, fractional_design_engine, tape_reinforcement)

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

# small-but-representative sizes so the suite stays fast
_SMALL = {
    'spiral_vase': lambda: spiral_vase(height=3, segments_per_layer=32, lobes=5),
    'ripple_vase': lambda: ripple_vase(height=2, ripples_per_layer=12, ripple_segments=2),
    'nonplanar_spacer': lambda: nonplanar_spacer(total_thickness=1.2, waves=3),
    'wave_bowl': lambda: wave_bowl(height=3, segments_per_layer=48, rim_waves=5),
    'twisted_polygon_vase': lambda: twisted_polygon_vase(height=3, segments_per_layer=48,
                                                         sides=5, twist_turns=0.5),
    'helical_screw': lambda: helical_screw(height=3, segments_per_layer=48, starts=2),
    'textured_cone': lambda: textured_cone(height=3, segments_per_layer=48, cells_up=4),
    'mobius_band': lambda: mobius_band(loop_segments=60, strokes_across=6),
    'trefoil_tube': lambda: trefoil_tube(tube_turns=16, cross_points=12),
    'towers_grid': lambda: towers_grid(rows=2, cols=2, layers=3),
    'snake_soapdish': lambda: snake_soapdish(height=8, waves=6, points_per_wave=8, length=40),
    'hex_adapter': lambda: hex_adapter(height=1.2),
    'lampshade': lambda: lampshade(height=3, segments_per_layer=48, ribs=6),
    'nuts_and_bolts': lambda: nuts_and_bolts(shaft_length=4, head_height=2, segments_per_layer=48),
    'star_polygon_lattice': lambda: star_polygon_lattice(cols=3, rows=2, layers=1),
    'phone_stand': lambda: phone_stand(stand_height=6, segments_per_layer=60),
    'pin_support_challenge': lambda: pin_support_challenge(height=4, segments_per_layer=32),
    'overhang_challenge': lambda: overhang_challenge(segments_per_layer=40, base_rings=3),
    'arc_vase': lambda: arc_vase(height=3, petals=6),
    'brush_lettering': lambda: brush_lettering(segments=60),
    'bead_studs': lambda: bead_studs(rows=2, cols=3, base_layers=1),
    'retraction_test': lambda: retraction_test(retractions=40),
    'blob_printing': lambda: blob_printing(rows=2, cols=3, blob_layers=1),
    'freeform_frosting': lambda: freeform_frosting(height=4, segments_per_layer=48),
    'fractional_design_engine': lambda: fractional_design_engine(points=80),
    'tape_reinforcement': lambda: tape_reinforcement(length=40, width=20, layers=2),
}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_generates_gcode(name):
    steps = _SMALL[name]()
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_simulates_to_a_real_print(name):
    steps = _SMALL[name]()
    r = fc.transform(steps, 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


@pytest.mark.parametrize('name', sorted(_SMALL))
def test_design_validates_without_errors(name):
    steps = _SMALL[name]()
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def _gcode(steps):
    return fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', initialization_data={'nozzle_temp': 210}), show_tips=False)


def test_reverse_engineer_recovers_vase_lobes_from_gcode():
    'From g-code alone, recover the lobe count, base radius and depth of a fluted vase.'
    from examples.reverse_engineer import reverse_engineer
    rep = reverse_engineer(_gcode(spiral_vase(radius=15, height=20, lobes=5, lobe_depth=2)))
    assert rep['modulation'] == 'radial'
    assert rep['radial_harmonic']['count'] == 5                 # exact lobe count
    assert abs(rep['base_radius'] - 15) < 0.5
    assert abs(rep['radial_harmonic']['amplitude'] - 2) < 0.3   # depth (cosine approx)
    assert rep['profile'] == 'cylinder'


def test_parse_gcode_strips_the_primer():
    'The FullControl primer (a wide bed sweep) must not contaminate the recovered point cloud.'
    from examples.reverse_engineer import parse_gcode
    import numpy as np
    gc = fc.transform(spiral_vase(radius=15, height=3), 'gcode', fc.GcodeControls(
        printer_name='generic',
        initialization_data={'nozzle_temp': 210, 'primer': 'front_lines_then_y'}), show_tips=False)
    assert '; START OF PRIMER PROCEDURE' in gc          # the primer is present in the g-code
    p = parse_gcode(gc)
    assert np.ptp(p[:, 0]) < 40                          # ~30 (the vase), not ~100 (the primer sweep)
    assert np.ptp(p[:, 1]) < 40


def test_reverse_engineer_recovers_polygon_sides():
    from examples.reverse_engineer import reverse_engineer
    poly = reverse_engineer(_gcode(twisted_polygon_vase(sides=6, morph_to_sides=0, twist_turns=0,
                                                        radius=18)))
    assert poly['radial_harmonic']['count'] == 6                # the hexagon


def test_identify_names_the_design_and_recovers_parameters():
    'Template-fit against the gallery: name the design + recover params (exact for the cosine vase).'
    from examples.reverse_engineer import identify
    r = identify(_gcode(spiral_vase(radius=15, height=20, lobes=5, lobe_depth=2)))
    assert r['design'] == 'spiral_vase'
    assert r['params']['lobes'] == 5
    assert abs(r['params']['radius'] - 15) < 0.5 and abs(r['params']['lobe_depth'] - 2) < 0.3
    assert r['fit_error'] < 1.0                       # regenerates close to the original


def test_identify_distinguishes_polygon_from_lobed_vase():
    from examples.reverse_engineer import identify
    poly = identify(_gcode(twisted_polygon_vase(sides=6, radius=18, twist_turns=0, morph_to_sides=0)))
    assert poly['design'] == 'twisted_polygon_vase' and poly['params']['sides'] == 6
    lobed = identify(_gcode(spiral_vase(lobes=6, lobe_depth=2)))
    assert lobed['design'] == 'spiral_vase'           # same count, but sine lobes -> not a polygon


def test_identify_recovers_snake_soapdish_wall():
    '''The Snake-Mode Soapdish is an open corrugated wall, not a surface of revolution: identify
    detects the open-wall case and recovers its corrugation count, length and height.'''
    from examples.reverse_engineer import identify
    r = identify(_gcode(snake_soapdish(waves=8, length=60, height=30, amplitude=6)))
    assert r['design'] == 'snake_soapdish'
    assert r['params']['waves'] == 8                  # exact corrugation count
    assert abs(r['params']['length'] - 60) < 6        # mid-height span
    assert abs(r['params']['height'] - 30) < 3
    assert abs(r['params']['amplitude'] - 6) < 1.5    # physical corrugation depth
    assert r['fit_error'] < 2.0                       # regenerates close to the original


def test_reverse_engineer_recovers_cone_taper():
    'A plain tapering cone is recovered as a cone profile from base to top radius.'
    from examples.reverse_engineer import reverse_engineer
    rep = reverse_engineer(_gcode(textured_cone(base_radius=24, top_radius=8, height=20,
                                                texture_depth=0)))
    assert rep['profile'] == 'cone/taper'
    assert abs(rep['base_radius'] - 24) < 1.0 and abs(rep['top_radius'] - 8) < 1.0


def test_gallery_registry_matches_callables():
    assert set(GALLERY) == {'spiral_vase', 'ripple_vase', 'nonplanar_spacer', 'wave_bowl',
                            'gyroid_infill', 'twisted_polygon_vase', 'helical_screw', 'textured_cone',
                            'mobius_band', 'trefoil_tube', 'towers_grid', 'snake_soapdish',
                            'hex_adapter', 'lampshade', 'nuts_and_bolts', 'star_polygon_lattice',
                            'phone_stand', 'pin_support_challenge', 'overhang_challenge',
                            'arc_vase', 'brush_lettering', 'bead_studs', 'retraction_test',
                            'blob_printing', 'freeform_frosting', 'fractional_design_engine',
                            'tape_reinforcement'}
    for fn in GALLERY.values():
        assert callable(fn)


def test_lobes_zero_is_a_plain_cylinder():
    'spiral_vase with no lobes: every point sits on the nominal radius.'
    steps = spiral_vase(radius=15, height=2, segments_per_layer=32, lobes=0, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]
    for p in pts:
        r = ((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5
        assert abs(r - 15) < 1e-9


def test_wave_bowl_rim_waves_ramp_in_from_a_smooth_base():
    '''The rim wave amplitude grows as height^2, so the base follows the smooth wall profile and
    only the lip ripples. Isolate the wave by differencing against an identical wave-free bowl.'''
    common = dict(opening_radius=25, base_radius=6, height=4, segments_per_layer=64,
                  rim_waves=6, centre=(50, 50))
    waved = [p for p in wave_bowl(rim_wave_amplitude=3, **common) if isinstance(p, Point)]
    smooth = [p for p in wave_bowl(rim_wave_amplitude=0, **common) if isinstance(p, Point)]

    def rad(p):
        return ((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5

    dev = [abs(rad(a) - rad(b)) for a, b in zip(waved, smooth)]  # pure wave contribution per point
    assert max(dev[:32]) < 0.2                      # base hugs the smooth profile (waves ~0)
    assert max(dev[-64:]) > 1.0                     # rim clearly ripples


def test_twisted_polygon_vase_cross_section_is_polygonal_and_twists():
    'A polygon cross-section varies in radius (vertices vs edge midpoints); the twist rotates it.'
    steps = twisted_polygon_vase(sides=5, radius=20, height=4, segments_per_layer=120,
                                 twist_turns=0.5, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    def polar(p):
        import math
        return (((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5, math.atan2(p.y - 50, p.x - 50))

    first_layer = [polar(p) for p in pts[:120]]
    radii = [r for r, _ in first_layer]
    assert max(radii) - min(radii) > 1.0            # polygonal: vertex radius > edge-midpoint radius

    # the twist rotates the polygon: the angle of the min-radius (an edge midpoint) at the base
    # differs from near the top
    def min_radius_angle(layer):
        return min(layer, key=lambda ra: ra[0])[1]
    top_layer = [polar(p) for p in pts[-120:]]
    assert abs(min_radius_angle(first_layer) - min_radius_angle(top_layer)) > 0.1


def test_morph_blends_vertex_count():
    'morph_to_sides changes the cross-section between base and rim (base != rim shape).'
    steps = twisted_polygon_vase(sides=3, morph_to_sides=8, radius=20, height=4,
                                 segments_per_layer=120, twist_turns=0, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    def radii(layer):
        return [((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5 for p in layer]
    base_spread = max(radii(pts[:120])) - min(radii(pts[:120]))    # triangle: large spread
    rim_spread = max(radii(pts[-120:])) - min(radii(pts[-120:]))   # octagon: smaller spread
    assert base_spread > rim_spread


def test_helical_screw_thread_is_present_and_climbs():
    'The thread modulates the radius, and its ridge angle shifts with height (a helix, not rings).'
    import math
    steps = helical_screw(radius=12, thread_depth=3, starts=1, pitch=8, height=6,
                          segments_per_layer=120, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    def polar(p):
        return (((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5, math.atan2(p.y - 50, p.x - 50))

    def ridge_angle(layer):
        return max(layer, key=lambda ra: ra[0])[1]      # angle of the thread crest

    bottom = [polar(p) for p in pts[:120]]
    top = [polar(p) for p in pts[-120:]]
    radii = [r for r, _ in bottom]
    assert max(radii) - min(radii) > 2.0                 # the thread stands out from the core
    assert abs(ridge_angle(bottom) - ridge_angle(top)) > 0.1   # crest rotates with height -> helix


def test_helical_screw_double_start_has_two_crests_per_turn():
    import math
    steps = helical_screw(radius=12, thread_depth=3, starts=2, height=2, segments_per_layer=240)
    layer = [(((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5, math.atan2(p.y - 50, p.x - 50))
             for p in [s for s in steps if isinstance(s, Point)][:240]]
    # count local radius maxima around one turn (a 2-start thread crests twice)
    rs = [r for r, _ in layer]
    crests = sum(1 for i in range(1, len(rs) - 1) if rs[i] > rs[i - 1] and rs[i] >= rs[i + 1])
    assert crests == 2


def test_mobius_band_has_a_half_twist_and_forms_a_loop():
    'The ribbon is flat where u=0 and vertical where u=pi (the half-twist), around a radius loop.'
    import math
    sa, ls = 8, 120
    steps = mobius_band(loop_radius=20, width=9, loop_segments=ls, strokes_across=sa, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]
    stroke = sa + 1

    def z_range(pp):
        return max(p.z for p in pp) - min(p.z for p in pp)

    assert z_range(pts[:stroke]) < 0.5                       # u=0: band lies flat
    mid = (ls // 2) * stroke
    assert z_range(pts[mid:mid + stroke]) > 8.0              # u=pi: band stands vertical (~width 9)
    radii = [math.hypot(p.x - 50, p.y - 50) for p in pts]
    assert min(radii) < 18 and max(radii) > 22              # a loop of radius ~20 (± width/2)


def test_snake_soapdish_is_a_corrugated_snake_mode_wall():
    '''The real FullControl Snake-Mode Soapdish: an OPEN corrugated wall (not a cup) printed in
    snake mode - print one way, step z up, print back, step up - with a lens silhouette (widest at
    mid-height) and fat 1mm lines.'''
    waves, ppw, length, h = 8, 12, 60.0, 16.0
    steps = snake_soapdish(length=length, height=h, waves=waves, points_per_wave=ppw,
                           centre=(70, 49))
    geom = steps[0]
    assert isinstance(geom, fc.ExtrusionGeometry)
    assert geom.width == 1.0                                  # FAT 1mm lines (snake mode loves flow)

    per_course = waves * ppw + 1
    pts = [s for s in steps if isinstance(s, Point)]
    courses = [pts[i:i + per_course] for i in range(0, len(pts), per_course)]
    assert len(courses) > 3

    # snake mode: z is held constant within a course and steps strictly up course to course
    for c in courses:
        assert max(p.z for p in c) - min(p.z for p in c) < 1e-9
    zs = [c[0].z for c in courses]
    assert all(b > a for a, b in zip(zs, zs[1:]))            # monotonic up (not a z-zigzag)

    # ...and the snake reverses direction each course (open wall, printed there-and-back)
    dirs = [c[-1].x - c[0].x for c in courses]
    assert all(a * b < 0 for a, b in zip(dirs, dirs[1:]))    # alternating left/right traverse

    # lens silhouette: the mid-height course is wider than the top and bottom courses
    def width(c):
        return max(p.x for p in c) - min(p.x for p in c)
    assert width(courses[len(courses) // 2]) > width(courses[0]) + 2
    assert width(courses[len(courses) // 2]) > width(courses[-1]) + 2

    # exactly `waves` corrugations across a mid course (perpendicular oscillation about the baseline)
    c = courses[len(courses) // 2]
    ys = [p.y for p in c]
    base = [sum(ys[max(0, i - 3):i + 4]) / len(ys[max(0, i - 3):i + 4]) for i in range(len(ys))]
    dev = [y - b for y, b in zip(ys, base)]
    peaks = sum(1 for i in range(1, len(dev) - 1) if dev[i] > dev[i - 1] and dev[i] >= dev[i + 1]
                and dev[i] > 0.5)
    assert peaks == waves


def test_optimization_passes_shrink_segments_and_insert_retractions():
    'merge_collinear collapses the subdivided edges; retract_on_travel guards the inter-tower hops.'
    rep = optimization_report(towers_grid(rows=2, cols=2, layers=4, points_per_edge=6))
    base, opt = rep['baseline'], rep['optimized']
    assert base['retractions'] == 0                     # the design itself has no retraction
    assert opt['segments'] < base['segments'] / 2       # merge_collinear: far fewer moves
    assert opt['retractions'] >= 2                       # retract_on_travel inserted some
    # the passes optimise the g-code without changing the physical print
    assert base['sim'].split(';')[0] == opt['sim'].split(';')[0]   # same time estimate


def test_trefoil_tube_is_a_closed_3d_tube():
    'A closed knot (last point returns to the first), genuinely 3D, swept into a tube_radius tube.'
    import math
    cp, tt, tr = 16, 20, 4.0
    steps = trefoil_tube(scale=6, tube_radius=tr, tube_turns=tt, cross_points=cp, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]
    from examples.trefoil_tube import _knot
    a, b = pts[0], pts[-1]
    assert math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) < 0.05          # closes on itself
    assert max(p.z for p in pts) - min(p.z for p in pts) > 8.0          # the knot oscillates in z
    # every point sits exactly tube_radius off the knot centre-line
    n, z_lift = tt * cp, 6 + tr + 0.8
    for i in (5, n // 3, n // 2):
        kx, ky, kz = _knot(i / n * math.tau, 6)
        centre_line = (50 + kx, 50 + ky, z_lift + kz)
        p = pts[i]
        assert abs(math.dist((p.x, p.y, p.z), centre_line) - tr) < 1e-9


def test_revolve_smooth_follows_the_profile_exactly():
    'With no texture, every point sits on profile(height_fraction) — the mapping is exact.'
    H = 4.0
    steps = revolve(profile=lambda f: 20 - 12 * f, texture=None, height=H,
                    segments_per_layer=48, centre=(50, 50))
    for p in (s for s in steps if isinstance(s, Point)):
        f = min(1.0, (p.z - 0.8) / H)
        r = ((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5
        assert abs(r - (20 - 12 * f)) < 1e-9


def test_textured_cone_tapers_and_carries_texture():
    'The cone narrows base->top, and the egg-crate texture pushes the radius off the smooth profile.'
    steps = textured_cone(base_radius=20, top_radius=8, height=4, cells_around=8, cells_up=6,
                          texture_depth=1.2, segments_per_layer=120, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    def rad(p):
        return ((p.x - 50) ** 2 + (p.y - 50) ** 2) ** 0.5
    base_r = sum(rad(p) for p in pts[:120]) / 120
    top_r = sum(rad(p) for p in pts[-120:]) / 120
    assert base_r > top_r + 5                        # clearly tapered
    # texture: within one turn the radius varies (cells_around bumps), beyond the smooth profile
    first_turn = [rad(p) for p in pts[:120]]
    assert max(first_turn) - min(first_turn) > 0.5


def test_print_time_study_sweeps_and_metrics_grow_with_size():
    from examples.print_time_study import sweep, study_table
    rows = sweep(spiral_vase, 'height', [4, 8, 12], segments_per_layer=48)
    assert len(rows) == 3
    assert all('total_time_s' in r and 'filament_length' in r for r in rows)
    times = [r['print_time_s'] for r in rows]
    filament = [r['filament_length'] for r in rows]
    assert times == sorted(times) and times[0] < times[-1]          # taller -> longer
    assert filament == sorted(filament) and filament[0] < filament[-1]
    table = study_table(rows, 'height')
    assert 'height' in table and 'filament_mm' in table
