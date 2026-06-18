"""Serialize the Toolpath IR to/from JSON - a stable, language-agnostic interchange format.

`resolve()` produces a Toolpath (an ordered stream of Segments, MaterialEvents and pass-through
non-motion steps). This module turns that stream into plain JSON and back, so a *non-Python*
consumer - the Rust g-code engine, p3d, a cached file - can drive the backends without re-running
resolve in Python. It is the boundary the native engine and cross-tool integrations build on.

Shape (version 1):

    {
      "version": 1,
      "events": [
        {"k": "segment", "start": [x,y,z], "end": [x,y,z], "travel": false, "speed": 1000.0,
         "length": 10.0, "deposited_volume": 1.8, "filament_length": 0.75, "source_index": 5,
         "kind": "line"|"arc", "centre": [cx,cy]|null, "clockwise": false,
         "width": 0.6, "height": 0.2, "color": [r,g,b]|null, "arc_points": [[x,y,z],...]|null},
        {"k": "material", "deposited_volume": 5.0, "filament_length": 2.0, "source_index": 9, "speed": 200.0},
        {"k": "step", "type": "ManualGcode", "data": {...}}   // any non-motion step, by class name
      ]
    }

Coordinates that are undefined in the IR (a None axis) serialize as JSON null and round-trip back to
None. Floats are kept at full precision so a consumer reproduces identical output.

Version 2 (opt-in via `to_dict(tp, version=2, ...)`) adds a self-describing, additive HEADER on top of
the identical `events` stream - it does not change a single event, so any v1 consumer that reads only
`events` (e.g. the Rust kernel) keeps working:

    {
      "version": 2,
      "units": {"length": "mm", "speed": "mm/min", "volume": "mm^3", "flow": "mm^3/s",
                "temperature": "degC", "angle": "deg"},     // the fixed FullControl conventions
      "generator": "fullcontrol <ver>",
      "provenance": {"design": "spiral_vase", "params": {...}} | null,   // what produced this toolpath
      "invariants": ["non_negative_extrusion", ...] | null,             // declared, checkable intent
      "events": [ ... identical to v1 ... ]
    }

`SCHEMA_VERSION` (the version emitted by default) stays 1, so existing output is byte-for-byte
unchanged; `LATEST_SCHEMA_VERSION` is 2 and `from_dict` accepts both. The recognised `invariants`
vocabulary is documented in docs/ir_spec.md and maps onto the existing validate / verify_gcode rules.
See docs/ir_spec.md for the full specification and docs/ir_prior_art.md for the standards survey.
"""
import json
from dataclasses import asdict

import fullcontrol
from fullcontrol.ir.toolpath import Toolpath, Segment, MaterialEvent

SCHEMA_VERSION = 1                       # the version to_dict emits by default (backward-compatible)
LATEST_SCHEMA_VERSION = 2                # the richest version this module understands
SUPPORTED_VERSIONS = (1, 2)

# The fixed FullControl unit conventions, made explicit and self-describing in v2 (UCUM-style codes).
UNITS = {
    'length': 'mm',
    'speed': 'mm/min',
    'volume': 'mm^3',
    'flow': 'mm^3/s',
    'temperature': 'degC',
    'angle': 'deg',
}

# Declared-invariant vocabulary recognised in the v2 header. Each maps to an existing checker (the
# validate backend / fullcontrol.gcode_engine.verify_gcode rules); see docs/ir_spec.md.
INVARIANTS = (
    'non_negative_extrusion',     # no segment retracts via deposited_volume < 0 (-> retraction_balance)
    'monotonic_layer_z',          # z never steps down within the build (-> negative-z / first-layer)
    'within_build_volume',        # all coordinates inside the declared build volume (-> bounds)
    'no_cold_extrusion',          # no extrusion before the hotend is hot (-> cold_extrusion)
    'bounded_flow',               # volumetric flow under the process ceiling (-> flow_rate_ceiling)
)


def _step_data(step) -> dict:
    'A pass-through step as a JSON-able dict (pydantic models dump their own fields).'
    if hasattr(step, 'model_dump'):
        return step.model_dump(mode='json')
    return dict(getattr(step, '__dict__', {}))


def to_dict(toolpath: Toolpath, *, version: int = SCHEMA_VERSION, provenance: dict = None,
            invariants: list = None) -> dict:
    '''The Toolpath IR as a plain dict (JSON-ready).

    version=1 (default): the original {"version", "events"} shape, byte-for-byte unchanged.
    version=2: prepends an additive, self-describing header (units / generator / provenance /
    invariants) onto the *identical* events stream. `provenance` records what produced the toolpath
    (e.g. {"design": ..., "params": ...}); `invariants` declares names from INVARIANTS this toolpath
    is intended to satisfy (checkable via the validate / verify_gcode rules).'''
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f'unsupported IR schema version {version!r} (supported: {SUPPORTED_VERSIONS})')
    events = []
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            events.append({'k': 'segment', **asdict(ev)})
        elif isinstance(ev, MaterialEvent):
            events.append({'k': 'material', **asdict(ev)})
        else:
            events.append({'k': 'step', 'type': type(ev).__name__, 'data': _step_data(ev)})
    if version == 1:
        return {'version': 1, 'events': events}
    bad = [n for n in (invariants or []) if n not in INVARIANTS]
    if bad:
        raise ValueError(f'unknown invariant(s) {bad} (recognised: {INVARIANTS})')
    return {'version': 2, 'units': dict(UNITS),
            'generator': f'fullcontrol {getattr(fullcontrol, "__version__", "")}'.strip(),
            'provenance': provenance, 'invariants': list(invariants) if invariants else None,
            'events': events}


def to_json(toolpath: Toolpath, indent=None, **kwargs) -> str:
    'Serialize to a JSON string. Extra kwargs (version/provenance/invariants) pass to to_dict.'
    return json.dumps(to_dict(toolpath, **kwargs), indent=indent)


def _tuple(v):
    return tuple(v) if isinstance(v, list) else v


def _tuple_of_tuples(v):
    return tuple(tuple(p) for p in v) if isinstance(v, list) else v


def _segment_from(e: dict) -> Segment:
    return Segment(
        start=_tuple(e['start']), end=_tuple(e['end']), travel=e['travel'], speed=e['speed'],
        length=e['length'], deposited_volume=e['deposited_volume'],
        filament_length=e['filament_length'], source_index=e['source_index'],
        kind=e.get('kind', 'line'), centre=_tuple(e.get('centre')), clockwise=e.get('clockwise', False),
        width=e.get('width'), height=e.get('height'), color=e.get('color'),
        arc_points=_tuple_of_tuples(e.get('arc_points')))


def _step_registry() -> dict:
    'Map step class name -> class, for rebuilding pass-through steps (the public fc.* step types).'
    import fullcontrol as fc
    from fullcontrol.core.base import BaseModelPlus
    reg = {}
    for name in dir(fc):
        obj = getattr(fc, name, None)
        if isinstance(obj, type) and issubclass(obj, BaseModelPlus):
            reg[name] = obj
    return reg


def from_dict(d: dict) -> Toolpath:
    '''Rebuild a Toolpath from `to_dict` output. Segments and MaterialEvents are reconstructed
    exactly; pass-through steps are rebuilt into their fc.* class when known, else kept as the raw
    {"type","data"} dict so nothing is silently lost.'''
    version = d.get('version')
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f'unsupported IR schema version {version!r} '
                         f'(supported: {SUPPORTED_VERSIONS})')
    # v2 adds only a header (units/generator/provenance/invariants); the events rebuild identically.
    reg = _step_registry()
    events = []
    for e in d['events']:
        kind = e.get('k')
        if kind == 'segment':
            events.append(_segment_from(e))
        elif kind == 'material':
            events.append(MaterialEvent(e['deposited_volume'], e['filament_length'],
                                        e['source_index'], e.get('speed')))
        elif kind == 'step':
            cls = reg.get(e['type'])
            events.append(cls(**e['data']) if cls is not None else e)
        else:
            raise ValueError(f'unknown IR event kind {kind!r}')
    return Toolpath(events)


def from_json(s: str) -> Toolpath:
    return from_dict(json.loads(s))
