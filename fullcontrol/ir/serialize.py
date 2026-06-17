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
"""
import json
from dataclasses import asdict

from fullcontrol.ir.toolpath import Toolpath, Segment, MaterialEvent

SCHEMA_VERSION = 1


def _step_data(step) -> dict:
    'A pass-through step as a JSON-able dict (pydantic models dump their own fields).'
    if hasattr(step, 'model_dump'):
        return step.model_dump(mode='json')
    return dict(getattr(step, '__dict__', {}))


def to_dict(toolpath: Toolpath) -> dict:
    'The Toolpath IR as a plain dict (JSON-ready).'
    events = []
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            events.append({'k': 'segment', **asdict(ev)})
        elif isinstance(ev, MaterialEvent):
            events.append({'k': 'material', **asdict(ev)})
        else:
            events.append({'k': 'step', 'type': type(ev).__name__, 'data': _step_data(ev)})
    return {'version': SCHEMA_VERSION, 'events': events}


def to_json(toolpath: Toolpath, indent=None) -> str:
    return json.dumps(to_dict(toolpath), indent=indent)


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
    if version != SCHEMA_VERSION:
        raise ValueError(f'unsupported IR schema version {version!r} (expected {SCHEMA_VERSION})')
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
