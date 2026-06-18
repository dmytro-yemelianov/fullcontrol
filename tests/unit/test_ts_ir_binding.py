"""Proof that the TypeScript authoring binding (ts/) emits valid, interchangeable Toolpath IR.

The fullcontrol-ts package under ts/ is a *front-end*: it authors a design in TypeScript and emits
the serialized v2 IR (the exact JSON `fullcontrol.ir.from_dict` consumes). The committed fixtures
ts/fixtures/*.ir.json were produced by running that TS package (`npm run fixtures` -> tsc + node).
This test loads them through the public Python IR API and proves:

  1. the TS-produced IR validates and round-trips (from_dict / to_dict), with a correct v2 header;
  2. simulating it yields sensible metrics (segment_count, total_time_s, extruded_volume > 0);
  3. the declared v2 invariants (non_negative_extrusion / monotonic_layer_z) actually pass;
  4. EQUIVALENCE: the TS square IR matches the SAME square authored in Python + resolve(), within a
     tight float tolerance — demonstrating the IR is interchangeable across front-ends.

This is the "many front-ends, one IR" claim made checkable. The test imports only the public API and
edits no Python module.
"""
import json
from pathlib import Path

import pytest

import fullcontrol as fc
from fullcontrol.ir import from_dict, to_dict, check_invariants, resolve
from fullcontrol.ir.serialize import UNITS
from fullcontrol.simulate.run import simulate_from_ir

FIXTURES = Path(__file__).resolve().parents[2] / 'ts' / 'fixtures'


def _load(name: str) -> dict:
    path = FIXTURES / name
    assert path.exists(), (
        f'missing TS-produced fixture {path}; regenerate with `cd ts && npm run fixtures`'
    )
    return json.loads(path.read_text())


# ---- 1. the TS IR is a valid v2 IR that round-trips ----

@pytest.mark.parametrize('name', ['square.ir.json', 'spiral.ir.json'])
def test_ts_fixture_is_valid_v2_ir(name):
    d = _load(name)
    assert d['version'] == 2
    assert d['units'] == UNITS  # the fixed FullControl conventions, emitted by the TS front-end
    assert d['generator'].startswith('fullcontrol-ts ')
    assert d['provenance'] is not None and 'design' in d['provenance']

    tp = from_dict(d)               # the public reader accepts the TS output as-is
    assert len(tp.events) == len(d['events'])

    # re-serialising the rebuilt toolpath reproduces the segment/material events byte-for-byte (the
    # load-bearing geometry+deposition data is lossless). Pass-through step events round-trip as a
    # SUPERSET: the TS front-end emits the minimal core fields and from_dict rebuilds them into the
    # registered fc.* class, which may add its own defaulted fields (e.g. Extruder.units/dia_feed) —
    # so a key-subset check is the correct equivalence for steps.
    # round-trip through JSON so tuple coords (to_dict) normalise to lists (as in the fixture)
    again = json.loads(json.dumps(to_dict(tp, version=2)))
    assert len(again['events']) == len(d['events'])
    for got, want in zip(again['events'], d['events']):
        assert got['k'] == want['k']
        if want['k'] in ('segment', 'material'):
            assert got == want
        else:  # step: type preserved, original data is a subset of the rebuilt data
            assert got['type'] == want['type']
            assert want['data'].items() <= got['data'].items()


# ---- 2. simulating the TS IR yields sensible metrics ----

def test_ts_square_simulates_sensibly():
    tp = from_dict(_load('square.ir.json'))
    r = simulate_from_ir(tp)
    assert r.segment_count == 4              # four extruding sides
    assert r.total_time_s > 0
    assert r.extruded_volume > 0
    assert r.filament_length > 0
    # square: 4 sides x 20 mm x (0.6 x 0.2) bead = 9.6 mm^3
    assert r.extruded_volume == pytest.approx(9.6, rel=1e-9)


def test_ts_spiral_simulates_sensibly():
    tp = from_dict(_load('spiral.ir.json'))
    r = simulate_from_ir(tp)
    assert r.segment_count > 100             # a continuous helix of many segments
    assert r.total_time_s > 0
    assert r.extruded_volume > 0
    assert r.filament_length > 0


# ---- 3. the declared invariants actually pass ----

@pytest.mark.parametrize('name', ['square.ir.json', 'spiral.ir.json'])
def test_ts_declared_invariants_hold(name):
    d = _load(name)
    declared = d.get('invariants') or []
    assert 'non_negative_extrusion' in declared
    assert 'monotonic_layer_z' in declared
    report = check_invariants(from_dict(d), declared, build_volume=(250, 250, 250))
    assert report.ok, report.summary()
    assert report.all_checked


def test_ts_spiral_is_a_monotonic_z_vase():
    # the vase invariant specifically: z of extruding moves never steps down
    d = _load('spiral.ir.json')
    report = check_invariants(from_dict(d), ['non_negative_extrusion', 'monotonic_layer_z'])
    report.raise_if_violated()  # would raise if the TS-authored helix retracted or dipped in z


# ---- 4. EQUIVALENCE: TS front-end IR == Python front-end IR for the same square ----

def _python_square_metrics():
    """Author the SAME square design in Python and resolve it to the IR, then simulate.

    Mirror of ts/src/designs.ts::square (size=20, origin=(50,50), z=0.2, bead 0.6x0.2). Resolved
    without printer procedures/primer (include_procedures=False) so only the user steps are folded —
    the TS front-end likewise emits only the authored steps. The `generic` printer's default speeds
    (print 1000 / travel 8000 mm/min) match the TS binding's defaults, so even time matches exactly.
    """
    ox, oy, z, size = 50, 50, 0.2, 20
    steps = [
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=ox, y=oy, z=z),
        fc.Extruder(on=True),
        fc.Point(x=ox + size, y=oy, z=z),
        fc.Point(x=ox + size, y=oy + size, z=z),
        fc.Point(x=ox, y=oy + size, z=z),
        fc.Point(x=ox, y=oy, z=z),
        fc.Extruder(on=False),
    ]
    controls = fc.GcodeControls(
        printer_name='generic',
        initialization_data={'extrusion_width': 0.6, 'extrusion_height': 0.2, 'dia_feed': 1.75},
    )
    tp = resolve(steps, controls, include_procedures=False, initial_extruder_on=False)
    return tp, simulate_from_ir(tp)


def test_ts_square_ir_equivalent_to_python_resolve():
    py_tp, py = _python_square_metrics()
    ts = simulate_from_ir(from_dict(_load('square.ir.json')))

    # the IR is interchangeable: identical aggregate metrics across the two front-ends
    assert ts.segment_count == py.segment_count
    assert ts.extruded_volume == pytest.approx(py.extruded_volume, rel=1e-9)
    assert ts.filament_length == pytest.approx(py.filament_length, rel=1e-9)
    assert ts.extruding_distance == pytest.approx(py.extruding_distance, rel=1e-9)
    assert ts.total_time_s == pytest.approx(py.total_time_s, rel=1e-9)


def test_ts_square_segment_geometry_matches_python():
    """Segment-level equivalence: the extruding XYZ path + per-segment deposition match Python."""
    py_tp, _ = _python_square_metrics()
    from fullcontrol.ir import Segment

    def extruding(tp):
        return [ev for ev in tp.events if isinstance(ev, Segment) and not ev.travel]

    ts_segs = extruding(from_dict(_load('square.ir.json')))
    py_segs = extruding(py_tp)
    assert len(ts_segs) == len(py_segs) == 4
    for a, b in zip(ts_segs, py_segs):
        assert a.start == pytest.approx(b.start, rel=1e-9)
        assert a.end == pytest.approx(b.end, rel=1e-9)
        assert a.length == pytest.approx(b.length, rel=1e-9)
        assert a.deposited_volume == pytest.approx(b.deposited_volume, rel=1e-9)
        assert a.filament_length == pytest.approx(b.filament_length, rel=1e-9)
