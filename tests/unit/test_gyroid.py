"""Tests for the gyroid_infill gallery design.

A gyroid infill is the striking 'only-in-FullControl' piece: ONE continuous bead (no
retractions, no travel jumps) approximating a gyroid TPMS inside a rectangular block. These
tests prove it generates real, printable gcode through every backend, that the bead is truly
continuous (no extruder-off steps), and that it has the gyroid-defining weave - the serpentine
direction alternates between successive layers and the path spans the whole block footprint.
"""
import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.gyroid_infill import gyroid_infill

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small():
    return gyroid_infill(size_x=12, size_y=12, height=2, cell_size=6, layer_height=0.3,
                         resolution=8)


def test_generates_gcode():
    gcode = fc.transform(_small(), 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert 'G1' in gcode                              # extruding moves emitted
    assert gcode.count('\n') > 20                     # a real toolpath, not a stub


def test_simulates_to_a_real_print():
    r = fc.transform(_small(), 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                       # material actually deposited
    assert r.extruding_distance > 0


def test_validates_without_errors():
    r = fc.transform(_small(), 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_first_step_is_extrusion_geometry():
    'Self-contained design: runs through every backend with no extra controls.'
    steps = _small()
    assert isinstance(steps[0], fc.ExtrusionGeometry)


def test_path_is_one_continuous_bead():
    'A gyroid bead is a single continuous toolpath: no extruder-off travels anywhere.'
    steps = _small()
    assert not any(isinstance(s, fc.Extruder) and s.on is False for s in steps)


def test_spans_the_full_block_footprint():
    'The toolpath reaches both ends of the block in x and y (around centre 50,50).'
    steps = gyroid_infill(size_x=20, size_y=16, height=2, cell_size=6, resolution=8,
                          centre=(50, 50))
    pts = [s for s in steps if isinstance(s, Point)]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    assert min(xs) <= 40.5 and max(xs) >= 59.5         # spans ~full 20mm in x
    assert min(ys) <= 42.5 and max(ys) >= 57.5         # spans ~full 16mm in y


def test_serpentine_direction_alternates_between_layers():
    '''The gyroid weave: one layer waves along x (long sweeps in x), the next along y. Group
    points by layer z and check the dominant travel axis flips between consecutive layers.'''
    steps = gyroid_infill(size_x=12, size_y=12, height=1.5, cell_size=6, layer_height=0.3,
                          resolution=8)
    pts = [s for s in steps if isinstance(s, Point)]

    layers = {}
    for p in pts:
        layers.setdefault(round(p.z, 6), []).append(p)
    zs = sorted(layers)
    assert len(zs) >= 3                                # several layers to compare

    def dominant_axis(layer_pts):
        # the sweep axis is the one each individual move steps along the most, on average:
        # tracks sweep steadily along their axis while only wiggling on the other
        dx = sum(abs(b.x - a.x) for a, b in zip(layer_pts, layer_pts[1:]))
        dy = sum(abs(b.y - a.y) for a, b in zip(layer_pts, layer_pts[1:]))
        return 'x' if dx > dy else 'y'

    axes = [dominant_axis(layers[z]) for z in zs]
    # consecutive layers must differ - this alternation is what makes it gyroid-like
    for a, b in zip(axes, axes[1:]):
        assert a != b
