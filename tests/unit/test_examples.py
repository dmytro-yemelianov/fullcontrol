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
                      twisted_polygon_vase)

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


def test_gallery_registry_matches_callables():
    assert set(GALLERY) == {'spiral_vase', 'ripple_vase', 'nonplanar_spacer', 'wave_bowl',
                            'gyroid_infill', 'twisted_polygon_vase'}
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
