"""Tests for the `blob_printing` gallery design.

Mirrors `tests/unit/test_examples.py`: the design must resolve cleanly through gcode, simulation
and validation on a generous build volume. Plus blob-specific checks: the step list contains one
`fc.StationaryExtrusion` per blob, and a width gradient makes the blob volumes vary.
"""
import pytest

import fullcontrol as fc
from fullcontrol.core.point import Point  # noqa: F401 - geometry helpers return core Points

from examples.blob_printing import blob_printing, _sphere_volume

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _small():
    # gradient + stacked blobs so all behaviours are exercised
    return blob_printing(rows=3, cols=4, blob_width=1.2, blob_width_max=2.0, blob_layers=2)


def _n_blobs(steps):
    return sum(1 for s in steps if isinstance(s, fc.StationaryExtrusion))


def test_starts_with_extrusion_geometry():
    steps = _small()
    assert isinstance(steps[0], fc.ExtrusionGeometry)


def test_generates_gcode():
    steps = _small()
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20
    assert 'G1' in gcode


def test_simulates_to_a_real_print():
    steps = _small()
    r = fc.transform(steps, 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0


def test_validates_without_errors():
    steps = _small()
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_blob_count_matches_sites_times_layers():
    rows, cols, layers = 3, 4, 2
    steps = blob_printing(rows=rows, cols=cols, blob_layers=layers)
    assert _n_blobs(steps) == rows * cols * layers


def test_uniform_width_gives_equal_blob_volumes():
    steps = blob_printing(rows=4, cols=4, blob_width=1.6)  # no blob_width_max => uniform
    vols = [s.volume for s in steps if isinstance(s, fc.StationaryExtrusion)]
    assert len(set(round(v, 9) for v in vols)) == 1
    # each blob is a sphere of the blob width
    assert vols[0] == pytest.approx(_sphere_volume(1.6))


def test_gradient_makes_blob_volumes_vary():
    steps = blob_printing(rows=4, cols=4, blob_width=0.8, blob_width_max=2.0)
    vols = [s.volume for s in steps if isinstance(s, fc.StationaryExtrusion)]
    assert len(set(round(v, 9) for v in vols)) > 1          # volumes genuinely vary
    assert vols[0] == pytest.approx(_sphere_volume(0.8))    # near corner = min width
    assert vols[-1] == pytest.approx(_sphere_volume(2.0))   # far corner = max width
    assert max(vols) > min(vols)


def test_overlap_controls_spacing():
    """Higher overlap packs blob sites closer (smaller XY extent)."""
    def extent(overlap):
        steps = blob_printing(rows=3, cols=3, blob_width=1.6, blob_overlap=overlap)
        xs = [s.x for s in steps if isinstance(s, fc.Point)]
        return max(xs) - min(xs)
    assert extent(50.0) < extent(0.0)


def _sim_volume(steps):
    return fc.transform(steps, 'simulation', _controls(), show_tips=False).extruded_volume


def test_blob_volume_reflected_in_extruded_volume():
    """The blob volumes show up in the simulation's extruded volume.

    The front_lines_then_y primer adds its own (constant) extrusion, so we isolate the blobs by a
    delta: each extra blob adds the same fixed increment to `extruded_volume`. Adding three more
    blobs must add exactly 3x that per-blob increment, proving the StationaryExtrusion blobs flow
    through simulation. (The simulator applies the printer's volume->E factor, so the increment is
    proportional to - not identical to - the raw mm^3 sphere volume; isolation is honest about that.)
    """
    v1 = _sim_volume(blob_printing(rows=1, cols=1, blob_width=1.6))
    v2 = _sim_volume(blob_printing(rows=1, cols=2, blob_width=1.6))
    v4 = _sim_volume(blob_printing(rows=1, cols=4, blob_width=1.6))
    per_blob = v2 - v1
    assert per_blob > 0
    assert (v4 - v1) == pytest.approx(3 * per_blob, rel=1e-6)   # blobs add linearly
    # the per-blob increment tracks blob width: wider blobs ooze more material
    v1_big = _sim_volume(blob_printing(rows=1, cols=1, blob_width=2.0))
    v2_big = _sim_volume(blob_printing(rows=1, cols=2, blob_width=2.0))
    assert (v2_big - v1_big) > per_blob


def test_default_tube_matches_reference_footprint():
    """The default (no rows/cols) builds the published tube: a ~20mm circle of blobs with a side
    spoke (~30mm X extent) stacked ten rings tall to z~8mm, matching `blob-printing.gcode`."""
    steps = blob_printing()
    pts = [s for s in steps if isinstance(s, fc.Point)]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    # reference extents: X 40.0..69.65 (29.6), Y 40.01..59.99 (20.0), z 0.76..7.96
    assert (max(xs) - min(xs)) == pytest.approx(29.6, abs=1.0)   # circle + lead-in spoke
    assert (max(ys) - min(ys)) == pytest.approx(20.0, abs=1.0)   # circle diameter
    assert min(zs) == pytest.approx(0.76, abs=0.01)
    assert max(zs) == pytest.approx(7.96, abs=0.01)


def test_default_is_a_stacked_circular_tube():
    """Blobs sit on a circle of radius ~10mm centred at (50, 50) across ten z-rings."""
    from math import hypot
    steps = blob_printing()
    pts = [s for s in steps if isinstance(s, fc.Point)]
    assert len(set(round(p.z, 3) for p in pts)) == 10          # ten stacked rings
    # ignore the straight lead-in spoke (Y==centre, X beyond the ring) when checking the circle
    ring = [p for p in pts if not (abs(p.y - 50.0) < 1e-6 and p.x > 60.5)]
    radii = [hypot(p.x - 50.0, p.y - 50.0) for p in ring]
    assert all(r == pytest.approx(10.0, abs=0.01) for r in radii)


def test_default_generates_valid_gcode():
    steps = blob_printing()
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]
    assert _n_blobs(steps) > 100                                # a real field of blobs


def test_rejects_bad_args():
    with pytest.raises(ValueError):
        blob_printing(rows=0)
    with pytest.raises(ValueError):
        blob_printing(blob_layers=0)
