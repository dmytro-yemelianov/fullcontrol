"""Freeform Frosting design: resolves/simulates/validates clean, and is a swirled, rippled,
tapering column (the soft-serve / piped-frosting silhouette of the FullControl challenge)."""
import math

import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point

from examples.freeform_frosting import freeform_frosting

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _small(**kw):
    p = dict(height=6, segments_per_layer=48)
    p.update(kw)
    return freeform_frosting(**p)


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data=_BUILD)


def _points(steps):
    return [s for s in steps if isinstance(s, Point)]


def _polar(p, cx=50.0, cy=50.0):
    return (math.hypot(p.x - cx, p.y - cy), math.atan2(p.y - cy, p.x - cx))


def test_starts_with_extrusion_geometry():
    geom = freeform_frosting()[0]
    assert isinstance(geom, fc.ExtrusionGeometry)
    assert geom.width > 0 and geom.height > 0


def test_design_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20
    assert 'G1' in gcode


def test_design_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0
    assert r.extruding_distance > 0


def test_design_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_column_swirls_phase_advances_with_height():
    """A fixed ripple feature (a ridge crest) rotates with height - the swirl. With swirl_turns>0
    the angle of the max-radius crest on a base turn differs from a top turn."""
    spt = 60
    steps = freeform_frosting(base_radius=15, height=8, segments_per_layer=spt, swirls=6,
                              swirl_turns=2.0, swirl_amplitude=80, peak=False, top_diameter=10,
                              centre=(50, 50))
    pts = _points(steps)

    def crest_angle(layer):
        return max((_polar(p) for p in layer), key=lambda ra: ra[0])[1]

    bottom = pts[:spt]
    top = pts[-spt:]
    assert abs(crest_angle(bottom) - crest_angle(top)) > 0.1


def test_straight_flutes_do_not_swirl():
    """With swirl_turns=0 the ridges are vertical: the crest angle is (nearly) constant up the column."""
    spt = 60
    steps = freeform_frosting(base_radius=15, height=8, segments_per_layer=spt, swirls=6,
                              swirl_turns=0.0, swirl_amplitude=80, peak=False, top_diameter=12,
                              centre=(50, 50))
    pts = _points(steps)

    def crest_angle(layer):
        return max((_polar(p) for p in layer), key=lambda ra: ra[0])[1]

    # crests repeat every 2*pi/swirls; with no swirl the crest sits at the same phase up the
    # column, so the angle difference (mod one ripple period) is ~0.
    period = math.tau / 6
    diff = (crest_angle(pts[:spt]) - crest_angle(pts[-spt:])) % period
    diff = min(diff, period - diff)                        # wrap to nearest period
    assert diff < 0.1


def test_radius_undulates_ripples_present():
    """Within one turn the radius varies by the ripple count - the fluting (not a smooth taper)."""
    spt = 240
    steps = freeform_frosting(base_radius=15, height=4, segments_per_layer=spt, swirls=7,
                              swirl_turns=0.0, swirl_amplitude=70, peak=False, top_diameter=14,
                              centre=(50, 50))
    pts = _points(steps)
    layer = [_polar(p) for p in pts[:spt]]
    radii = [r for r, _ in layer]
    assert max(radii) - min(radii) > 1.0                  # clearly rippled
    # count radius maxima around one turn -> matches the ripple count
    crests = sum(1 for i in range(1, len(radii) - 1)
                 if radii[i] > radii[i - 1] and radii[i] >= radii[i + 1])
    assert crests == 7


def test_peak_tapers_the_top_to_a_tip():
    """peak=True: the top is much narrower than mid-height (the soft-serve tip)."""
    spt = 48
    steps = freeform_frosting(base_radius=15, height=10, segments_per_layer=spt, peak=True,
                              swirl_amplitude=30, centre=(50, 50))
    pts = _points(steps)

    def mean_r(layer):
        return sum(_polar(p)[0] for p in layer) / len(layer)

    mid = len(pts) // 2
    mid_r = mean_r(pts[mid - spt // 2:mid + spt // 2])
    top_r = mean_r(pts[-spt:])
    assert top_r < mid_r * 0.5                              # top clearly tapers below the middle
    assert top_r < 2.0                                     # comes (nearly) to a point


def test_column_tapers_from_base_to_top():
    """The base is wider than the top (a frosting cone, not a cylinder)."""
    spt = 48
    steps = freeform_frosting(base_radius=15, height=10, segments_per_layer=spt, peak=False,
                              top_diameter=8, swirl_amplitude=20, centre=(50, 50))
    pts = _points(steps)

    def mean_r(layer):
        return sum(_polar(p)[0] for p in layer) / len(layer)

    assert mean_r(pts[:spt]) > mean_r(pts[-spt:]) + 5


def test_concave_offset_bulges_the_midsection():
    """A positive concave_offset pushes the mid-height silhouette outward versus a straight taper."""
    spt = 48
    common = dict(base_radius=12, height=10, segments_per_layer=spt, peak=False, top_diameter=8,
                  swirl_amplitude=0, swirl_turns=0, centre=(50, 50))
    straight = _points(freeform_frosting(concave_offset=0, **common))
    bulged = _points(freeform_frosting(concave_offset=6, **common))
    mid = len(straight) // 2

    def mean_r(layer):
        return sum(_polar(p)[0] for p in layer) / len(layer)

    band = slice(mid - spt // 2, mid + spt // 2)
    assert mean_r(bulged[band]) > mean_r(straight[band]) + 2


@pytest.mark.parametrize('vary_fan,vary_speed', [(True, False), (False, True), (True, True)])
def test_checkboxes_emit_commands_and_still_print(vary_fan, vary_speed):
    steps = _small(vary_fan=vary_fan, vary_speed=vary_speed)
    if vary_fan:
        assert any(isinstance(s, fc.Fan) for s in steps)
    if vary_speed:
        assert any(isinstance(s, fc.Printer) for s in steps)
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]
