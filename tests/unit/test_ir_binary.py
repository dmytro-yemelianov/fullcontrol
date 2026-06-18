"""The Toolpath IR columnar binary encoding (fullcontrol/ir/binary.py).

The binary form must round-trip the *same* Toolpath as the JSON form, drive a backend
identically, and be markedly more compact for a large design.
"""
import math

import fullcontrol as fc
from fullcontrol.ir import (resolve, to_bytes, from_bytes, read_header, to_json,
                            from_json, SCHEMA_VERSION)
from fullcontrol.ir.binary import MAGIC
from fullcontrol.ir.toolpath import Segment, MaterialEvent, Toolpath


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})


def _feature_rich():
    'arcs, extruder toggles, a geometry change, stationary extrusion, a manual command.'
    return [
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
        fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
        fc.ManualGcode(text='; hello'),
        fc.Point(x=0, y=30, z=0.2),
        fc.Extruder(on=False),
        fc.StationaryExtrusion(volume=5.0, speed=200),
        fc.Point(x=0, y=0, z=0.4),
    ]


def _spiral_vase(turns=6000):
    'A many-segment design (one move per point) for the size comparison.'
    steps = [fc.ExtrusionGeometry(width=0.6, height=0.2), fc.Extruder(on=True)]
    for i in range(turns):
        a = i * 0.1
        steps.append(fc.Point(x=20 * math.cos(a), y=20 * math.sin(a), z=0.2 + i * 0.0005))
    return steps


def test_magic_and_header():
    tp = resolve(_feature_rich(), _controls())
    b = to_bytes(tp)
    assert b[:4] == MAGIC == b'FCIR'
    h = read_header(b)
    assert h['format_version'] == 1
    assert h['schema_version'] == SCHEMA_VERSION
    assert h['n_segments'] == sum(1 for e in tp.events if isinstance(e, Segment))
    assert h['n_material'] == sum(1 for e in tp.events if isinstance(e, MaterialEvent))


def test_segments_round_trip_field_by_field():
    'Arcs, lines, width/height all survive the binary round-trip exactly.'
    tp = resolve(_feature_rich(), _controls())
    back = from_bytes(to_bytes(tp))
    orig = [e for e in tp.events if isinstance(e, Segment)]
    got = [e for e in back.events if isinstance(e, Segment)]
    assert orig and len(orig) == len(got)
    for a, b in zip(orig, got):
        assert a == b                       # frozen dataclass equality across every field
        assert isinstance(b.start, tuple)
        if b.centre is not None:
            assert isinstance(b.centre, tuple)
    # at least one arc and one line in the fixture, so both kinds are exercised
    assert any(s.kind == 'arc' for s in got) and any(s.kind == 'line' for s in got)


def test_material_events_round_trip():
    tp = resolve(_feature_rich(), _controls())
    a = [e for e in tp.events if isinstance(e, MaterialEvent)]
    b = [e for e in from_bytes(to_bytes(tp)).events if isinstance(e, MaterialEvent)]
    assert a and a == b


def test_passthrough_steps_rebuild_like_json():
    'Pass-through steps come back identically to the JSON path (same registry rebuild).'
    tp = resolve(_feature_rich(), _controls())
    back_b = from_bytes(to_bytes(tp))
    back_j = from_json(to_json(tp))
    assert len(back_b.events) == len(back_j.events) == len(tp.events)
    for x, y in zip(back_b.events, back_j.events):
        assert type(x) is type(y)
        if isinstance(x, (Segment, MaterialEvent)):
            assert x == y
    manual = [e for e in back_b.events if isinstance(e, fc.ManualGcode)]
    assert any(m.text == '; hello' for m in manual)


def test_event_order_preserved():
    'Segments / material / steps interleave back in the original print order.'
    tp = resolve(_feature_rich(), _controls())
    back = from_bytes(to_bytes(tp))

    def kinds(events):
        out = []
        for e in events:
            out.append('s' if isinstance(e, Segment)
                       else 'm' if isinstance(e, MaterialEvent) else 'p')
        return out

    assert kinds(back.events) == kinds(tp.events)


def test_undefined_axis_round_trips_as_none():
    seg = Segment(start=(None, None, None), end=(1.0, 2.0, None), travel=True, speed=6000,
                  length=0.0, deposited_volume=0.0, filament_length=0.0, source_index=0)
    back = from_bytes(to_bytes(Toolpath([seg])))
    s = back.events[0]
    assert s.start == (None, None, None)
    assert s.end == (1.0, 2.0, None)
    assert s == seg


def test_none_width_height_and_speed_round_trip():
    'None width/height (parsed-gcode style) and a None material speed survive as None.'
    seg = Segment(start=(0.0, 0.0, 0.0), end=(1.0, 0.0, 0.0), travel=False, speed=1000,
                  length=1.0, deposited_volume=0.1, filament_length=0.05, source_index=3,
                  width=None, height=None)
    mat = MaterialEvent(2.0, 1.0, 4, speed=None)
    back = from_bytes(to_bytes(Toolpath([seg, mat])))
    assert back.events[0].width is None and back.events[0].height is None
    assert back.events[0] == seg
    assert back.events[1].speed is None and back.events[1] == mat


def test_binary_drives_backend_identically():
    'simulate_from_ir(from_bytes(to_bytes(tp))) == simulate_from_ir(tp) for the key metrics.'
    from fullcontrol.simulate.run import simulate_from_ir
    tp = resolve(_feature_rich(), _controls())
    r0 = simulate_from_ir(tp)
    r1 = simulate_from_ir(from_bytes(to_bytes(tp)))
    for field in ('total_time_s', 'extruded_volume', 'filament_length',
                  'segment_count', 'max_flow_rate'):
        assert getattr(r0, field) == getattr(r1, field), field


def test_binary_is_smaller_than_json_for_large_design():
    tp = resolve(_spiral_vase(), _controls())
    n = sum(1 for e in tp.events if isinstance(e, Segment))
    assert n >= 5000
    bin_len = len(to_bytes(tp))
    json_len = len(to_json(tp))
    print(f'\nspiral vase: {n} segments — binary {bin_len} B, json {json_len} B, '
          f'ratio {json_len / bin_len:.2f}x smaller')
    assert bin_len < json_len


def test_large_design_round_trips_exactly():
    'Field-for-field segment equality across thousands of segments.'
    tp = resolve(_spiral_vase(2000), _controls())
    back = from_bytes(to_bytes(tp))
    orig = [e for e in tp.events if isinstance(e, Segment)]
    got = [e for e in back.events if isinstance(e, Segment)]
    assert orig == got and len(orig) >= 2000


def test_v2_metadata_survives_round_trip():
    'provenance / invariants / units are exposed via read_header after a binary round-trip.'
    tp = resolve(_feature_rich(), _controls())
    prov = {'design': 'spiral_vase', 'params': {'lobes': 5}}
    inv = ['non_negative_extrusion', 'monotonic_layer_z']
    b = to_bytes(tp, provenance=prov, invariants=inv)
    h = read_header(b)
    assert h['provenance'] == prov
    assert h['invariants'] == inv
    assert h['units'] == {'length': 'mm', 'speed': 'mm/min', 'volume': 'mm^3',
                          'flow': 'mm^3/s', 'temperature': 'degC', 'angle': 'deg'}
    assert h['generator'].startswith('fullcontrol')
    # the events still round-trip unchanged regardless of the header
    assert from_bytes(b).events and isinstance(from_bytes(b), Toolpath)


def test_unknown_invariant_rejected():
    import pytest
    tp = resolve(_feature_rich(), _controls())
    with pytest.raises(ValueError):
        to_bytes(tp, invariants=['not_a_real_invariant'])


def test_bad_magic_rejected():
    import pytest
    with pytest.raises(ValueError):
        read_header(b'XXXX' + b'\x00' * 20)
