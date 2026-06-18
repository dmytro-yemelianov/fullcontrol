"""The brush_lettering plaque: a single continuous bead whose extrusion width is modulated per
segment, like a calligraphy brush stroke. These tests prove (a) it resolves cleanly through all
backends, and (b) the headline capability - the step list emits MANY distinct ExtrusionGeometry
widths spanning ~min_width..max_width, and the width tracks the intended stroke law (fat on the
downstroke, hairline on the upstroke).
"""
import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.brush_lettering import brush_lettering

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}

_STROKES = ['sine', 'loop', 'signature']


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small(stroke):
    return brush_lettering(stroke=stroke, segments=120, min_width=0.4, max_width=1.4)


def _widths_along_points(steps):
    '''Walk the step list, pairing every Point with the ExtrusionGeometry width in force when it was
    emitted. Returns a list of (Point, width) in path order - the bead as actually printed.'''
    out, w = [], None
    for s in steps:
        if isinstance(s, fc.ExtrusionGeometry):
            w = s.width
        elif isinstance(s, Point):
            out.append((s, w))
    return out


@pytest.mark.parametrize('stroke', _STROKES)
def test_design_generates_gcode(stroke):
    gcode = fc.transform(_small(stroke), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


@pytest.mark.parametrize('stroke', _STROKES)
def test_design_simulates_to_a_real_print(stroke):
    r = fc.transform(_small(stroke), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


@pytest.mark.parametrize('stroke', _STROKES)
def test_design_validates_without_errors(stroke):
    r = fc.transform(_small(stroke), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_starts_with_its_own_extrusion_geometry():
    steps = _small('signature')
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].height == pytest.approx(0.3)


@pytest.mark.parametrize('stroke', _STROKES)
def test_emits_many_distinct_widths_spanning_the_range(stroke):
    '''THE KEY TEST: per-segment variable width. The step list contains MANY distinct
    ExtrusionGeometry widths, spanning ~min_width..max_width - calligraphic line weight that a
    normal slicer (one fixed width) can never produce.'''
    min_w, max_w = 0.4, 1.4
    steps = brush_lettering(stroke=stroke, segments=200, min_width=min_w, max_width=max_w)
    widths = sorted({s.width for s in steps if isinstance(s, fc.ExtrusionGeometry)})
    assert len(widths) > 1                              # not a single fixed width
    assert len(widths) > 10                             # genuinely swelling/thinning along the bead
    assert all(min_w - 1e-9 <= w <= max_w + 1e-9 for w in widths)   # every width inside the range
    # the modulation actually reaches near both extremes (a real swell from hairline to fat)
    span = max_w - min_w
    assert widths[0] <= min_w + 0.15 * span            # gets near the hairline
    assert widths[-1] >= min_w + 0.85 * span           # gets near the fattest


def test_width_tracks_the_downstroke_law():
    '''The default width law is broad-pen calligraphy: fattest where the stroke goes DOWN, thinnest
    where it goes UP. For the 'sine' stroke (y oscillates), the widest bead must sit on a descending
    segment and the thinnest on an ascending segment.'''
    steps = brush_lettering(stroke='sine', segments=200, min_width=0.4, max_width=1.4)
    samples = _widths_along_points(steps)
    ys = [p.y for p, _ in samples]
    ws = [w for _, w in samples]

    def local_slope(i):
        a, b = max(0, i - 1), min(len(ys) - 1, i + 1)
        return ys[b] - ys[a]

    i_fat = max(range(len(ws)), key=lambda i: ws[i])
    i_thin = min(range(len(ws)), key=lambda i: ws[i])
    assert local_slope(i_fat) < 0                       # fattest bead is on a downstroke
    assert local_slope(i_thin) > 0                      # hairline is on an upstroke

    # and globally: descending samples are, on average, wider than ascending ones
    down = [w for i, w in enumerate(ws) if local_slope(i) < 0]
    up = [w for i, w in enumerate(ws) if local_slope(i) > 0]
    assert sum(down) / len(down) > sum(up) / len(up)


def test_custom_width_fn_is_respected_and_constant_fn_gives_one_width():
    'A custom width_fn drives the bead; a constant width_fn collapses to a single fixed width.'
    const = brush_lettering(stroke='sine', segments=120, min_width=0.4, max_width=1.4,
                            width_fn=lambda t: 0.5)
    widths = {s.width for s in const if isinstance(s, fc.ExtrusionGeometry)}
    assert len(widths) == 1                            # constant fn -> one fixed width
    assert widths.pop() == pytest.approx(0.9)          # 0.4 + 0.5*(1.4-0.4)

    # a ramp width_fn (0 -> 1 along the path) should hit both ends of the range
    ramp = brush_lettering(stroke='sine', segments=120, min_width=0.4, max_width=1.4,
                           width_fn=lambda t: t)
    rw = sorted({s.width for s in ramp if isinstance(s, fc.ExtrusionGeometry)})
    assert rw[0] == pytest.approx(0.4) and rw[-1] == pytest.approx(1.4)


def test_varying_width_deposits_more_than_a_hairline_bead():
    '''The varying-width bead deposits a volume between an all-hairline and an all-fat bead of the
    same path - proof the width modulation reaches the simulated material, not just the step list.'''
    common = dict(stroke='sine', segments=160, min_width=0.4, max_width=1.4)
    varied = fc.transform(brush_lettering(**common), 'simulation', _controls(), show_tips=False)
    thin = fc.transform(brush_lettering(width_fn=lambda t: 0.0, **common), 'simulation',
                        _controls(), show_tips=False)
    fat = fc.transform(brush_lettering(width_fn=lambda t: 1.0, **common), 'simulation',
                       _controls(), show_tips=False)
    assert thin.extruded_volume < varied.extruded_volume < fat.extruded_volume


def test_single_continuous_bead_with_no_internal_travel():
    'One continuous stroke: every point extrudes (no Extruder(on=False)/travel hops mid-bead).'
    steps = _small('signature')
    assert not any(isinstance(s, fc.Extruder) for s in steps)   # extrusion never toggled off
    pts = [s for s in steps if isinstance(s, Point)]
    assert len(pts) > 100                                       # a substantial single bead


def test_unknown_stroke_and_bad_args_raise():
    with pytest.raises(ValueError):
        brush_lettering(stroke='nope')
    with pytest.raises(TypeError):
        brush_lettering(stroke='sine', width_fn=123)
    with pytest.raises(ValueError):
        brush_lettering(min_width=1.0, max_width=0.5)
