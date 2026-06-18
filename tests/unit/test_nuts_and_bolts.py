"""The Nuts and Bolts design: a hex head morphing into a helical-threaded shaft, one continuous bead.

Mirrors tests/unit/test_examples.py: the design must resolve to a real g-code toolpath, simulate to a
real print (time/volume > 0), and validate clean against a generous build volume. Plus geometry
asserts proving the head carries a hexagonal cross-section and the shaft carries a climbing helix.
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.nuts_and_bolts import nuts_and_bolts

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small():
    # small-but-representative bolt so the suite stays fast
    return nuts_and_bolts(shaft_length=4.0, head_height=1.5, head_blend=1.0,
                          segments_per_layer=64, layer_height=0.2)


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


def test_first_step_is_extrusion_geometry():
    steps = _small()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.6


def test_head_cross_section_is_hexagonal():
    '''The head region is a regular hexagon: six radial maxima (across-corners) around one layer,
    with the vertex radius clearly larger than the edge-midpoint radius.'''
    spl = 240
    steps = nuts_and_bolts(head_width=21, head_height=2.0, head_blend=1.0, shaft_length=3.0,
                           segments_per_layer=spl, layer_height=0.2, centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    # first full turn sits inside the hex head (head_height=2 >> one 0.2mm layer)
    layer = [(math.hypot(p.x - 50, p.y - 50), math.atan2(p.y - 50, p.x - 50)) for p in pts[:spl]]
    radii = [r for r, _ in layer]
    assert max(radii) - min(radii) > 1.0            # polygonal: vertices stand out from edge midpoints

    # count radial maxima around the turn -> a hexagon crests six times. roll so the array starts at
    # the global minimum (an edge midpoint), keeping every corner in the interior away from the seam.
    lo = radii.index(min(radii))
    rolled = radii[lo:] + radii[:lo]
    rs = [rolled[-1]] + rolled + [rolled[0]]         # pad both ends to count circularly
    mean_r = sum(radii) / len(radii)
    crests = sum(1 for i in range(1, len(rs) - 1)
                 if rs[i] > rs[i - 1] and rs[i] >= rs[i + 1] and rs[i] > mean_r)
    assert crests == 6                               # six hexagon corners


def test_shaft_carries_a_helical_thread_that_climbs():
    '''The shaft radius is modulated by a thread, and the thread crest angle advances with height
    (a helix, not stacked rings).'''
    spl = 200
    steps = nuts_and_bolts(shaft_diameter=6, thread_pitch=1.25, thread_depth=0.6, shaft_length=12,
                           head_height=1.0, head_blend=1.0, segments_per_layer=spl, layer_height=0.2,
                           centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]

    def polar(p):
        return (math.hypot(p.x - 50, p.y - 50), math.atan2(p.y - 50, p.x - 50), p.z)

    # restrict to the threaded shaft (above the head + blend region)
    shaft = [polar(p) for p in pts if p.z > 0.8 + 3.0]
    radii = [r for r, _, _ in shaft]
    assert max(radii) - min(radii) > 0.4            # the thread stands out from the core (~thread_depth)

    def crest_angle(layer):
        return max(layer, key=lambda t: t[0])[1]    # angle of the thread crest

    bottom = shaft[:spl]
    top = shaft[-spl:]
    assert abs(crest_angle(bottom) - crest_angle(top)) > 0.1   # crest rotates with height -> helix


def test_thread_depth_zero_is_a_smooth_shaft():
    'With no thread depth, every shaft point sits exactly on the core radius (a plain cylinder).'
    steps = nuts_and_bolts(shaft_diameter=6, thread_depth=0, shaft_length=4, head_height=0.0,
                           head_blend=0.0, segments_per_layer=64, layer_height=0.2, centre=(50, 50))
    for p in (s for s in steps if isinstance(s, Point)):
        r = math.hypot(p.x - 50, p.y - 50)
        assert abs(r - 3.0) < 1e-9
