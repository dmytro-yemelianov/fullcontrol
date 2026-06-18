"""The Toolpath IR JSON interchange format (fullcontrol/ir/serialize.py)."""
import json

import fullcontrol as fc
from fullcontrol.ir import resolve, to_dict, to_json, from_dict, from_json, SCHEMA_VERSION
from fullcontrol.ir.serialize import LATEST_SCHEMA_VERSION, SUPPORTED_VERSIONS, UNITS
from fullcontrol.ir.toolpath import Segment, MaterialEvent


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


def test_to_json_is_valid_versioned_json():
    tp = resolve(_feature_rich(), _controls())
    doc = json.loads(to_json(tp))
    assert doc['version'] == SCHEMA_VERSION
    kinds = {e['k'] for e in doc['events']}
    assert kinds <= {'segment', 'material', 'step'}
    assert 'segment' in kinds and 'material' in kinds and 'step' in kinds


def test_segment_round_trips_field_by_field():
    tp = resolve(_feature_rich(), _controls())
    back = from_json(to_json(tp))
    orig_segs = [e for e in tp.events if isinstance(e, Segment)]
    back_segs = [e for e in back.events if isinstance(e, Segment)]
    assert len(orig_segs) == len(back_segs) and orig_segs
    for a, b in zip(orig_segs, back_segs):
        assert a == b                      # frozen dataclass equality across every field
        assert isinstance(b.start, tuple)  # lists came back as tuples
        if b.centre is not None:
            assert isinstance(b.centre, tuple)


def test_material_event_round_trips():
    tp = resolve(_feature_rich(), _controls())
    a = [e for e in tp.events if isinstance(e, MaterialEvent)]
    b = [e for e in from_dict(to_dict(tp)).events if isinstance(e, MaterialEvent)]
    assert a and a == b


def test_passthrough_steps_rebuild_into_fc_classes():
    tp = resolve(_feature_rich(), _controls())
    back = from_dict(to_dict(tp))
    manual = [e for e in back.events if isinstance(e, fc.ManualGcode)]
    assert any(m.text == '; hello' for m in manual)  # our step, among the procedure comments


def test_round_tripped_ir_simulates_identically():
    'The deserialized IR must drive a backend to the same result as the original.'
    from fullcontrol.simulate.run import simulate_from_ir
    tp = resolve(_feature_rich(), _controls())
    r0 = simulate_from_ir(tp)
    r1 = simulate_from_ir(from_json(to_json(tp)))
    for field in ('total_time_s', 'extruded_volume', 'filament_length', 'segment_count', 'max_flow_rate'):
        assert getattr(r0, field) == getattr(r1, field), field


def test_undefined_axis_round_trips_as_none():
    seg = Segment(start=(None, None, None), end=(1.0, 2.0, None), travel=True, speed=6000,
                  length=0.0, deposited_volume=0.0, filament_length=0.0, source_index=0)
    from fullcontrol.ir.toolpath import Toolpath
    back = from_dict(to_dict(Toolpath([seg])))
    s = back.events[0]
    assert s.start == (None, None, None)
    assert s.end == (1.0, 2.0, None)


def test_unknown_version_rejected():
    import pytest
    with pytest.raises(ValueError, match='schema version'):
        from_dict({'version': 999, 'events': []})


def test_v1_is_the_default_emitted_version():
    'Default output stays v1, byte-for-byte unchanged, so existing consumers are not disturbed.'
    tp = resolve(_feature_rich(), _controls())
    assert SCHEMA_VERSION == 1 and LATEST_SCHEMA_VERSION == 2
    doc = to_dict(tp)
    assert doc['version'] == 1
    assert 'units' not in doc and 'provenance' not in doc      # v1 carries no header


def test_v2_adds_units_provenance_and_invariants_header():
    tp = resolve(_feature_rich(), _controls())
    doc = to_dict(tp, version=2,
                  provenance={'design': 'spiral_vase', 'params': {'lobes': 5}},
                  invariants=['non_negative_extrusion', 'monotonic_layer_z'])
    assert doc['version'] == 2
    # units are declared and self-describing (the FullControl conventions)
    assert doc['units'] == UNITS
    assert UNITS['length'] == 'mm' and UNITS['speed'] == 'mm/min' and UNITS['volume'] == 'mm^3'
    assert doc['units']['flow'] == 'mm^3/s' and doc['units']['temperature'] == 'degC'
    assert doc['generator'].startswith('fullcontrol')
    assert doc['provenance'] == {'design': 'spiral_vase', 'params': {'lobes': 5}}
    assert doc['invariants'] == ['non_negative_extrusion', 'monotonic_layer_z']
    # the event stream is byte-for-byte the v1 stream (the header is purely additive)
    assert doc['events'] == to_dict(tp)['events']


def test_v2_round_trips_events_identically_to_v1():
    tp = resolve(_feature_rich(), _controls())
    from_v2 = from_dict(to_dict(tp, version=2, provenance={'design': 'x'}))
    from_v1 = from_dict(to_dict(tp))
    assert from_v2.events == from_v1.events                    # the header doesn't affect rebuild
    assert 2 in SUPPORTED_VERSIONS and 1 in SUPPORTED_VERSIONS


def test_v2_simulates_identically():
    from fullcontrol.simulate.run import simulate_from_ir
    tp = resolve(_feature_rich(), _controls())
    r = simulate_from_ir(from_json(to_json(tp, version=2)))
    r0 = simulate_from_ir(tp)
    for field in ('total_time_s', 'extruded_volume', 'segment_count'):
        assert getattr(r, field) == getattr(r0, field), field
