"""``travel_reorder`` - reduce inter-island travel within each Z-layer.

Within a single Z-layer the toolpath is a sequence of *extrusion islands* (contiguous runs of
extruding moves) separated by travel moves. Re-ordering the islands does not change what is
printed, only the order in which the nozzle visits them, so we re-order them by nearest-neighbour
plus a 2-opt refinement to cut total travel distance. Each island's *internal* segments are kept
byte-identical (same objects, same order); only the connecting travel moves between islands are
re-synthesised. No segment crosses a Z-layer boundary, so seams/collision risk is unchanged.
"""
from math import hypot

from fullcontrol.ir.passes import register_pass
from fullcontrol.ir.toolpath import Segment, Toolpath


def _z(seg: Segment):
    'The (rounded) Z of a segment endpoint, for layer bucketing.'
    z = seg.end[2] if seg.end[2] is not None else seg.start[2]
    return None if z is None else round(z, 6)


def _xy(p):
    return (p[0], p[1])


def _dist(a, b):
    if a[0] is None or b[0] is None or a[1] is None or b[1] is None:
        return 0.0
    return hypot(b[0] - a[0], b[1] - a[1])


def _split_layer(events):
    '''Split a flat event list into maximal runs that share a Z-layer (extruding moves define
    the layer; non-extruding/non-Segment events attach to the current run). Returns a list of
    (z, sub_events) preserving order.'''
    runs = []
    cur, cur_z = [], None
    for ev in events:
        z = _z(ev) if isinstance(ev, Segment) and not ev.travel else None
        if z is not None and cur_z is not None and z != cur_z and cur:
            runs.append((cur_z, cur))
            cur = []
        if z is not None:
            cur_z = z
        cur.append(ev)
    if cur:
        runs.append((cur_z, cur))
    return runs


def _islands(events):
    '''Partition a single-layer run into (prefix, islands, suffix).

    An island is a maximal contiguous list of events whose Segments all extrude (non-motion
    events between extruding moves stay inside the island). `prefix` is everything before the
    first island (leading travels/setup); `suffix` is everything after the last island.'''
    islands = []
    cur = []
    prefix = []
    started = False
    pending_travel = []  # travels/non-extruding between islands
    for ev in events:
        is_travel = isinstance(ev, Segment) and ev.travel
        is_extrude = isinstance(ev, Segment) and not ev.travel
        if is_extrude:
            if not started:
                prefix = pending_travel
                pending_travel = []
                started = True
                cur = [ev]
            else:
                if pending_travel:  # a travel closed the previous island
                    islands.append(cur)
                    cur = [ev]
                    pending_travel = []
                else:
                    cur.append(ev)
        elif is_travel:
            if started:
                pending_travel.append(ev)
            else:
                pending_travel.append(ev)
        else:  # non-motion event
            if started and not pending_travel:
                cur.append(ev)
            elif started:
                pending_travel.append(ev)
            else:
                pending_travel.append(ev)
    if started:
        islands.append(cur)
    suffix = pending_travel
    if not started:
        prefix = pending_travel
        suffix = []
    return prefix, islands, suffix


def _island_endpoints(island):
    'The XY entry (first extruding start) and exit (last extruding end) of an island.'
    extrudes = [e for e in island if isinstance(e, Segment) and not e.travel]
    return _xy(extrudes[0].start), _xy(extrudes[-1].end)


def _order(islands, start_xy):
    'Nearest-neighbour ordering of islands from start_xy, then 2-opt on the visiting order.'
    n = len(islands)
    ends = [_island_endpoints(isl) for isl in islands]  # (entry, exit)

    # nearest-neighbour
    remaining = set(range(n))
    order = []
    cur = start_xy
    while remaining:
        nxt = min(remaining, key=lambda i: _dist(cur, ends[i][0]))
        order.append(nxt)
        cur = ends[nxt][1]
        remaining.discard(nxt)

    def travel_cost(seq):
        cost = _dist(start_xy, ends[seq[0]][0])
        for a, b in zip(seq, seq[1:]):
            cost += _dist(ends[a][1], ends[b][0])
        return cost

    # 2-opt: reverse sub-ranges while it strictly reduces travel
    improved = True
    while improved:
        improved = False
        base = travel_cost(order)
        for i in range(n - 1):
            for k in range(i + 1, n):
                cand = order[:i] + order[i:k + 1][::-1] + order[k + 1:]
                if travel_cost(cand) < base - 1e-9:
                    order = cand
                    base = travel_cost(cand)
                    improved = True
    return order


def _travel_between(a_exit, b_entry, template):
    'A travel Segment from a_exit to b_entry, copying speed/geometry from a template travel.'
    z = template.end[2] if template is not None else None
    start = (a_exit[0], a_exit[1], z)
    end = (b_entry[0], b_entry[1], z)
    length = _dist(a_exit, b_entry)
    speed = template.speed if template is not None else 0.0
    return Segment(start, end, True, speed, length, 0.0, 0.0,
                   template.source_index if template is not None else 0, kind='line')


def _reorder_layer(events):
    'Reorder islands within one layer to cut travel; return the rebuilt event list.'
    prefix, islands, suffix = _islands(events)
    if len(islands) < 2:
        return events
    # the nozzle position entering the islands: exit of the last prefix motion, else first entry
    start_xy = None
    for ev in reversed(prefix):
        if isinstance(ev, Segment):
            start_xy = _xy(ev.end)
            break
    if start_xy is None:
        start_xy = _island_endpoints(islands[0])[0]

    order = _order(islands, start_xy)
    template = next((e for e in events if isinstance(e, Segment) and e.travel), None)

    out = list(prefix)
    prev_exit = start_xy
    for idx in order:
        entry, exit_ = _island_endpoints(islands[idx])
        if _dist(prev_exit, entry) > 0:
            out.append(_travel_between(prev_exit, entry, template))
        out.extend(islands[idx])
        prev_exit = exit_
    out.extend(suffix)
    return out


def travel_reorder(toolpath: Toolpath) -> Toolpath:
    '''Reorder extrusion islands within each Z-layer (nearest-neighbour + 2-opt) to reduce total
    travel distance. Island internals are byte-identical; no cross-layer reordering; extruding
    material is conserved.'''
    out = []
    for _z_val, run in _split_layer(toolpath.events):
        out.extend(_reorder_layer(run))
    return Toolpath(out)


register_pass('travel_reorder', travel_reorder)
