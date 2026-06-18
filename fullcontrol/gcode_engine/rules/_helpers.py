"""Shared helpers for the verification rules."""
from fullcontrol.ir import Segment


def segments(toolpath):
    '''Yield (segment_index, line, segment) for every Segment in the toolpath, where
    segment_index is the 0-based position in the Segment stream and line is the 1-based g-code
    line number (the parser stores it in `source_index`).'''
    out = []
    idx = 0
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            out.append((idx, ev.source_index, ev))
            idx += 1
    return out


def extruding(seg):
    'True for a real extruding move (not a travel, has length and deposited material).'
    return (not seg.travel) and seg.length and seg.length > 0


def is_planar(toolpath, threshold=0.5):
    '''True unless > `threshold` fraction of moves change z (non-planar / continuous-z printing),
    in which case the layer-based overhang/seam rules are unreliable and should be skipped.'''
    segs = [s for _, _, s in segments(toolpath)]
    if not segs:
        return True
    z_changes = 0
    moves = 0
    for s in segs:
        if None in s.start or None in s.end:
            continue
        moves += 1
        if abs(s.end[2] - s.start[2]) > 1e-9:
            z_changes += 1
    if moves == 0:
        return True
    return (z_changes / moves) <= threshold


def layer_of(z, layer_height, base_z):
    'Bucket a z height into an integer layer index (best-effort, for grouping moves by layer).'
    if z is None or not layer_height or layer_height <= 0:
        return None
    return round((z - base_z) / layer_height)
