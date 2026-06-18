"""Tape-Reinforcement Research Demo: a flat multi-layer coupon that PAUSES for tape to be embedded.

Mirrors tests/unit/test_examples.py - the design must resolve to g-code, simulate to a real print
and validate clean (on a long bed). The key behaviour of this design is the manual-intervention
PAUSE: a pause command is emitted in the gap before each layer in `tape_layers`, so a strip of
reinforcing tape / fibre can be laid by hand and then printed over. These tests pin that the number
of pauses is parametric (== number of tape layers) and that the part is a long, flat, multi-layer
strip.
"""
import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)

from examples.tape_reinforcement import tape_reinforcement

# the strip is up to ~150 mm long, so it needs a long bed (build_volume_y:300)
_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 300, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


# small-but-representative coupon so the suite stays fast (still a real strip and a real pause)
def _small(**kw):
    params = dict(length=80.0, width=20.0, layers=4, tape_layers=(2,), infill=0.6)
    params.update(kw)
    return tape_reinforcement(**params)


def test_starts_with_its_own_extrusion_geometry():
    steps = _small()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.6 and steps[0].height == 0.2


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


def test_pause_count_is_parametric_and_emitted_in_gcode():
    'The KEY behaviour: one pause command per tape layer, present verbatim in the g-code.'
    for tape_layers, pause in [((2,), 'M0'), ((1, 3), 'M0'), ((2, 4), 'M600')]:
        steps = _small(layers=5, tape_layers=tape_layers, pause_gcode=pause)
        # one ManualGcode pause step per tape layer, in the design itself
        pause_steps = [s for s in steps if isinstance(s, fc.ManualGcode) and pause in s.text]
        assert len(pause_steps) == len(tape_layers)
        # ...and exactly that many in the emitted g-code (as standalone command lines)
        gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
        n = sum(1 for line in gcode.splitlines() if line.strip().startswith(pause))
        assert n == len(tape_layers)


def test_tape_layers_are_clamped_and_deduplicated():
    'Out-of-range / duplicate tape layers do not produce spurious or missing pauses.'
    steps = tape_reinforcement(layers=3, tape_layers=(0, 2, 2, 9), pause_gcode='M0')
    pauses = [s for s in steps if isinstance(s, fc.ManualGcode)]
    assert len(pauses) == 1                          # only the in-range, unique layer 2 survives


def test_specimen_is_a_long_flat_multilayer_strip():
    'A multi-layer flat strip: `layers` distinct z levels and a long-rectangle footprint.'
    length, width, layers = 150.0, 40.0, 4
    steps = tape_reinforcement(length=length, width=width, layers=layers, layer_height=0.2,
                               origin=(30.0, 30.0))
    pts = [s for s in steps if isinstance(s, Point)]
    assert len(pts) > 0

    zs = sorted({round(p.z, 6) for p in pts})
    assert len(zs) == layers                         # one distinct z level per layer (multi-layer)
    assert abs(zs[0] - 0.2) < 1e-9                   # first layer one layer-height off the bed
    assert all(abs((b - a) - 0.2) < 1e-9 for a, b in zip(zs, zs[1:]))   # evenly stacked

    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    assert abs(x_span - length) < 1e-6               # footprint matches length x width...
    assert abs(y_span - width) < 1e-6
    assert x_span > y_span                           # ...and it is a LONG strip (length > width)


def test_layers_are_solid_raster_fills():
    'Each layer is many parallel raster lines spanning the full length (a solid fill, not an outline).'
    length, width = 80.0, 20.0
    steps = tape_reinforcement(length=length, width=width, layers=1, infill=0.6, origin=(30.0, 30.0))
    pts = [s for s in steps if isinstance(s, Point)]
    # raster lines run the full length in x; every move spans (close to) the whole length
    assert max(p.x for p in pts) - min(p.x for p in pts) > length - 1e-6
    # enough parallel lines to fill the width solidly (~width/infill lines, each 2 endpoints)
    assert len(pts) >= 2 * int(width / 0.6)
