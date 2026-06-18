"""Columnar binary encoding for the Toolpath IR — the compact, zero-copy-friendly
form alongside the JSON of `serialize.py`.

This is the Arrow-shaped binary ABI promised by `docs/ir_spec.md` §4 and the
prior-art Apache Arrow recommendation: instead of one JSON object per event, the
Segment stream is stored as a struct-of-arrays of contiguous little-endian columns
(exactly the layout of `columnar.ColumnarToolpath`), so a consumer can `frombuffer`
each column with zero per-value parsing. It round-trips the *same* `Toolpath` as the
JSON form — segments, material events and pass-through steps — and is markedly smaller
for large designs (no key names, no decimal text; raw float64 columns).

=====================================================================================
BYTE LAYOUT  (all multi-byte integers/floats are LITTLE-ENDIAN)
=====================================================================================

    magic        4 bytes   b'FCIR'
    format_ver   uint16    binary container format version (currently 1)
    flags        uint16    reserved, 0
    meta_len     uint32    byte length of the metadata block
    meta         meta_len  UTF-8 JSON metadata block (see below)
    <column region>        the packed arrays, in the order meta['columns'] lists,
                           each at meta['offsets'][name] for meta['counts'] rows

The metadata block is a small JSON object — it carries everything needed to recover
the layout, so the file is fully self-describing:

    {
      "format_version": 1,
      "schema_version": 2,                 # the JSON IR schema this mirrors
      "units": {...},                      # the v2 header units (serialize.UNITS)
      "generator": "fullcontrol <ver>",
      "provenance": {...} | null,          # v2 header provenance
      "invariants": [...] | null,          # v2 header invariants
      "n_segments": <int>,
      "n_material": <int>,
      "event_order": [...],                # one tag per event, in print order, so the
                                           # interleaving of segments / material / steps
                                           # is reconstructed exactly. tags:
                                           #   "s" = segment   (next seg column row)
                                           #   "m" = material  (next material row)
                                           #   "p" = step      (next pass-through step)
      "steps": [ {"type": ..., "data": {...}} | <raw dict> ],   # pass-through steps (rare)
      "seg_extra": { "<row>": {"centre": [..]|null, "color": [..]|null,
                               "arc_points": [[...],...]|null} },  # per-arc/colour extras
      "columns": [ "start", "end", "travel", "speed", "length",
                   "deposited_volume", "filament_length", "source_index",
                   "kind", "width", "height", "material" ],
      "offsets": { "<col>": <byte offset from start of column region> },
      "nbytes":  { "<col>": <byte length> }
    }

Column region — one contiguous block per column, in `columns` order:

    start              n_segments * 3 * float64   (x,y,z; None axis -> NaN)
    end                n_segments * 3 * float64
    travel             n_segments * uint8         (1/0)
    speed              n_segments * float64
    length             n_segments * float64
    deposited_volume   n_segments * float64
    filament_length    n_segments * float64
    source_index       n_segments * int64
    kind               n_segments * uint8         (0 = line, 1 = arc)
    width              n_segments * float64       (None -> NaN)
    height             n_segments * float64       (None -> NaN)
    material           n_material  * float64, laid out as rows of
                       (deposited_volume, filament_length, source_index, speed);
                       source_index stored as float64 (exact for realistic indices),
                       speed None -> NaN.  i.e. n_material * 4 * float64.

=====================================================================================
DESIGN RATIONALE
=====================================================================================

* Arrow-like contiguous columns. The numeric heart of a Segment (start/end/speed/
  length/volumes/width/height) is packed as raw `numpy.tobytes()` and read back with
  `numpy.frombuffer` — no per-value (de)serialisation, near-zero-copy on read. This is
  the same struct-of-arrays `columnar.py` already uses for the vectorised fast-path.
* NaN for a null axis / undefined width/height, mirroring `columnar.py`. `from_bytes`
  maps NaN back to `None` so a `(None, None, None)` start round-trips exactly.
* JSON tail for the rare and irregular. Pass-through steps, arc `centre`/`clockwise`/
  `arc_points`, and per-move `color` are infrequent or ragged; packing them as fixed
  columns would waste space and complexity, so they live in the JSON metadata
  (`steps` / `seg_extra`). The hot, uniform numeric columns stay binary.
* Self-describing. `columns`/`offsets`/`nbytes`/`counts` in the header mean the layout
  is recoverable without hard-coding it in the reader.

CAVEATS
-------
* Endianness: the format is fixed little-endian. `to_bytes` forces little-endian
  numpy dtypes; `from_bytes` reads them as little-endian regardless of host order, so
  a big-endian host round-trips correctly (numpy byte-swaps on read).
* `source_index` for material events is stored via float64; exact for all realistic
  step indices (< 2**53). Segment `source_index` uses int64 (exact).
* Pass-through steps are handled identically to the JSON form (rebuilt into their
  `fc.*` class when known, else kept as the raw `{type,data}` dict), via the JSON tail
  — so binary and JSON have the same fidelity and the same "unknown class" behaviour.
"""
import json

import numpy as np

import fullcontrol
from fullcontrol.ir.serialize import (SCHEMA_VERSION, UNITS, INVARIANTS, _step_data,
                                      _step_registry)
from fullcontrol.ir.toolpath import Toolpath, Segment, MaterialEvent

MAGIC = b'FCIR'
FORMAT_VERSION = 1

# float64 / int64 / uint8 little-endian dtypes — the wire types for the columns.
_F64 = np.dtype('<f8')
_I64 = np.dtype('<i8')
_U8 = np.dtype('<u1')

# segment columns packed as raw numeric arrays (name -> (dtype, components-per-row))
_SEG_COLUMNS = (
    ('start', _F64, 3), ('end', _F64, 3), ('travel', _U8, 1), ('speed', _F64, 1),
    ('length', _F64, 1), ('deposited_volume', _F64, 1), ('filament_length', _F64, 1),
    ('source_index', _I64, 1), ('kind', _U8, 1), ('width', _F64, 1), ('height', _F64, 1),
)


def _nan_if_none(v):
    return np.nan if v is None else v


def _none_if_nan(v):
    f = float(v)
    return None if f != f else f  # NaN != NaN


def _xyz_to_tuple(row):
    'A 3-float column row back to an (x, y, z) tuple, NaN -> None.'
    return tuple(_none_if_nan(c) for c in row)


def to_bytes(toolpath: Toolpath, *, provenance: dict = None, invariants: list = None) -> bytes:
    '''The Toolpath IR as a compact little-endian binary blob (see module docstring for
    the exact layout). Round-trips the same Toolpath as `serialize.to_dict`: segments and
    material events are packed as contiguous columns, pass-through steps + arc/colour extras
    travel in the JSON metadata block. `provenance`/`invariants` mirror the v2 JSON header.'''
    bad = [n for n in (invariants or []) if n not in INVARIANTS]
    if bad:
        raise ValueError(f'unknown invariant(s) {bad} (recognised: {INVARIANTS})')

    segs, materials, steps = [], [], []
    event_order, seg_extra = [], {}
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            event_order.append('s')
            segs.append(ev)
        elif isinstance(ev, MaterialEvent):
            event_order.append('m')
            materials.append(ev)
        else:
            event_order.append('p')
            steps.append({'type': type(ev).__name__, 'data': _step_data(ev)})

    n = len(segs)
    # Build the segment columns as numpy arrays.
    start = np.empty((n, 3), dtype=_F64)
    end = np.empty((n, 3), dtype=_F64)
    travel = np.empty(n, dtype=_U8)
    speed = np.empty(n, dtype=_F64)
    length = np.empty(n, dtype=_F64)
    deposited_volume = np.empty(n, dtype=_F64)
    filament_length = np.empty(n, dtype=_F64)
    source_index = np.empty(n, dtype=_I64)
    kind = np.empty(n, dtype=_U8)
    width = np.empty(n, dtype=_F64)
    height = np.empty(n, dtype=_F64)
    for i, s in enumerate(segs):
        start[i] = [_nan_if_none(c) for c in s.start]
        end[i] = [_nan_if_none(c) for c in s.end]
        travel[i] = 1 if s.travel else 0
        speed[i] = _nan_if_none(s.speed)
        length[i] = s.length
        deposited_volume[i] = s.deposited_volume
        filament_length[i] = s.filament_length
        source_index[i] = s.source_index
        kind[i] = 1 if s.kind == 'arc' else 0
        width[i] = _nan_if_none(s.width)
        height[i] = _nan_if_none(s.height)
        # ragged / rare per-segment fields -> JSON tail (keyed by row index)
        extra = {}
        if s.centre is not None:
            extra['centre'] = list(s.centre)
        if s.clockwise:
            extra['clockwise'] = True
        if s.color is not None:
            extra['color'] = list(s.color)
        if s.arc_points is not None:
            extra['arc_points'] = [list(p) for p in s.arc_points]
        if s.kind != 'line' and 'centre' not in extra:
            extra['kind'] = s.kind  # non-line kind without a centre (defensive)
        if extra:
            seg_extra[str(i)] = extra

    col_arrays = {
        'start': start, 'end': end, 'travel': travel, 'speed': speed, 'length': length,
        'deposited_volume': deposited_volume, 'filament_length': filament_length,
        'source_index': source_index, 'kind': kind, 'width': width, 'height': height,
    }

    # Material events as a (n_material, 4) float64 block.
    nm = len(materials)
    material = np.empty((nm, 4), dtype=_F64)
    for i, m in enumerate(materials):
        material[i] = (m.deposited_volume, m.filament_length, float(m.source_index),
                       _nan_if_none(m.speed))
    col_arrays['material'] = material

    # Lay out the column region, recording offsets/sizes for the header.
    column_names = [c[0] for c in _SEG_COLUMNS] + ['material']
    offsets, nbytes, blobs = {}, {}, []
    cursor = 0
    for name in column_names:
        raw = np.ascontiguousarray(col_arrays[name]).tobytes()
        offsets[name] = cursor
        nbytes[name] = len(raw)
        blobs.append(raw)
        cursor += len(raw)

    meta = {
        'format_version': FORMAT_VERSION,
        'schema_version': SCHEMA_VERSION,
        'units': dict(UNITS),
        'generator': f'fullcontrol {getattr(fullcontrol, "__version__", "")}'.strip(),
        'provenance': provenance,
        'invariants': list(invariants) if invariants else None,
        'n_segments': n,
        'n_material': nm,
        'event_order': event_order,
        'steps': steps,
        'seg_extra': seg_extra,
        'columns': column_names,
        'offsets': offsets,
        'nbytes': nbytes,
    }
    meta_bytes = json.dumps(meta, separators=(',', ':')).encode('utf-8')

    header = bytearray()
    header += MAGIC
    header += np.array([FORMAT_VERSION], dtype='<u2').tobytes()
    header += np.array([0], dtype='<u2').tobytes()          # flags
    header += np.array([len(meta_bytes)], dtype='<u4').tobytes()
    return bytes(header) + meta_bytes + b''.join(blobs)


def read_header(data: bytes) -> dict:
    '''The metadata block of a binary IR blob (format/schema version, units, generator,
    provenance, invariants, counts, layout) without decoding the column region.'''
    if data[:4] != MAGIC:
        raise ValueError('not a FullControl binary IR blob (bad magic)')
    fmt = int(np.frombuffer(data, dtype='<u2', count=1, offset=4)[0])
    if fmt != FORMAT_VERSION:
        raise ValueError(f'unsupported binary IR format version {fmt} (expected {FORMAT_VERSION})')
    meta_len = int(np.frombuffer(data, dtype='<u4', count=1, offset=8)[0])
    meta = json.loads(data[12:12 + meta_len].decode('utf-8'))
    return meta


def from_bytes(data: bytes) -> Toolpath:
    '''Rebuild a Toolpath from `to_bytes` output. Columns are read with `numpy.frombuffer`
    (zero-copy, byte-swapped on a big-endian host); segments/material/steps are reassembled
    in their original print order via the header `event_order`.'''
    meta = read_header(data)
    meta_len = int(np.frombuffer(data, dtype='<u4', count=1, offset=8)[0])
    region = memoryview(data)[12 + meta_len:]
    offsets, nbytes = meta['offsets'], meta['nbytes']

    def col(name, dtype, comps):
        off, size = offsets[name], nbytes[name]
        arr = np.frombuffer(region, dtype=dtype, count=size // dtype.itemsize, offset=off)
        return arr.reshape(-1, comps) if comps > 1 else arr

    n = meta['n_segments']
    start = col('start', _F64, 3)
    end = col('end', _F64, 3)
    travel = col('travel', _U8, 1)
    speed = col('speed', _F64, 1)
    length = col('length', _F64, 1)
    deposited_volume = col('deposited_volume', _F64, 1)
    filament_length = col('filament_length', _F64, 1)
    source_index = col('source_index', _I64, 1)
    kind = col('kind', _U8, 1)
    width = col('width', _F64, 1)
    height = col('height', _F64, 1)
    seg_extra = meta.get('seg_extra', {})

    segments = []
    for i in range(n):
        extra = seg_extra.get(str(i), {})
        centre = tuple(extra['centre']) if extra.get('centre') is not None else None
        color = list(extra['color']) if extra.get('color') is not None else None
        arc_points = (tuple(tuple(p) for p in extra['arc_points'])
                      if extra.get('arc_points') is not None else None)
        seg_kind = 'arc' if int(kind[i]) == 1 else extra.get('kind', 'line')
        segments.append(Segment(
            start=_xyz_to_tuple(start[i]), end=_xyz_to_tuple(end[i]),
            travel=bool(travel[i]), speed=_none_if_nan(speed[i]), length=float(length[i]),
            deposited_volume=float(deposited_volume[i]),
            filament_length=float(filament_length[i]), source_index=int(source_index[i]),
            kind=seg_kind, centre=centre, clockwise=bool(extra.get('clockwise', False)),
            width=_none_if_nan(width[i]), height=_none_if_nan(height[i]),
            color=color, arc_points=arc_points))

    nm = meta['n_material']
    mat = col('material', _F64, 4) if nm else np.empty((0, 4))
    materials = [MaterialEvent(float(mat[i, 0]), float(mat[i, 1]), int(mat[i, 2]),
                               _none_if_nan(mat[i, 3])) for i in range(nm)]

    # Rebuild pass-through steps into their fc.* class (else keep the raw dict), as the JSON form does.
    reg = _step_registry()
    rebuilt_steps = []
    for e in meta.get('steps', []):
        if isinstance(e, dict) and 'type' in e and 'data' in e:
            cls = reg.get(e['type'])
            rebuilt_steps.append(cls(**e['data']) if cls is not None else e)
        else:
            rebuilt_steps.append(e)

    # Interleave back into print order using event_order.
    si = mi = pi = 0
    events = []
    for tag in meta['event_order']:
        if tag == 's':
            events.append(segments[si]); si += 1
        elif tag == 'm':
            events.append(materials[mi]); mi += 1
        else:
            events.append(rebuilt_steps[pi]); pi += 1
    return Toolpath(events)
