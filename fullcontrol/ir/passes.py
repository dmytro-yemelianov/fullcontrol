"""IR -> IR optimization passes.

The Toolpath IR is the natural home for slicer-style optimizations: each pass is a pure
function `Toolpath -> Toolpath` that runs after `resolve()` and before the backend folds, so
every backend (gcode, plot, simulate, validate) sees the optimized toolpath. Passes are
opt-in - enabled via `initialization_data['optimize']` - so default output is unchanged.

`optimize` is a list whose entries are either a pass name, or a `(name, params)` pair, e.g.
``initialization_data={'optimize': ['merge_collinear', ('retract_on_travel', {'min_distance': 5})]}``.
"""
from fullcontrol.ir.toolpath import Toolpath, Segment

_PASSES = {}


def register_pass(name: str, fn) -> None:
    'Register an IR->IR pass (a function Toolpath -> Toolpath) under a name.'
    _PASSES[name] = fn


def available_passes() -> list:
    return sorted(_PASSES)


def get_pass(name: str):
    if name not in _PASSES:
        raise ValueError(f'unknown optimization pass {name!r}. Available: {available_passes()}')
    return _PASSES[name]


def apply_passes(toolpath: Toolpath, specs) -> Toolpath:
    'Apply a list of pass specs (name or (name, params)) in order.'
    for spec in specs:
        name, params = (spec, {}) if isinstance(spec, str) else (spec[0], spec[1])
        toolpath = get_pass(name)(toolpath, **params)
    return toolpath


# --------------------------------------------------------------------------- #
# merge_collinear: combine consecutive collinear line moves into one
# --------------------------------------------------------------------------- #

def _vec(a, b):
    'b - a per axis, treating an undefined (None) axis as no change (0).'
    return tuple(0.0 if a[i] is None or b[i] is None else b[i] - a[i] for i in range(3))


def _collinear(p, q, r, tol) -> bool:
    'True if p->q and q->r point the same way (cross ~ 0 and dot > 0).'
    u, v = _vec(p, q), _vec(q, r)
    cx = u[1] * v[2] - u[2] * v[1]
    cy = u[2] * v[0] - u[0] * v[2]
    cz = u[0] * v[1] - u[1] * v[0]
    if (cx * cx + cy * cy + cz * cz) > tol * tol:
        return False
    return (u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) > 0


def _mergeable(a: Segment, b: Segment, tol) -> bool:
    return (a.kind == 'line' and b.kind == 'line' and a.travel == b.travel
            and a.speed == b.speed and a.width == b.width and a.height == b.height
            and a.end == b.start and _collinear(a.start, a.end, b.end, tol))


def merge_collinear(toolpath: Toolpath, tol: float = 1e-6) -> Toolpath:
    '''Merge consecutive collinear line moves (same travel/speed/geometry) into a single move,
    summing length and deposited material. Geometrically identical, fewer gcode lines.'''
    out = []
    for ev in toolpath.events:
        if isinstance(ev, Segment) and out and isinstance(out[-1], Segment) and _mergeable(out[-1], ev, tol):
            a = out[-1]
            out[-1] = Segment(a.start, ev.end, a.travel, a.speed, a.length + ev.length,
                              a.deposited_volume + ev.deposited_volume,
                              a.filament_length + ev.filament_length, a.source_index,
                              kind='line', width=a.width, height=a.height, color=ev.color)
        else:
            out.append(ev)
    return Toolpath(out)


register_pass('merge_collinear', merge_collinear)


# --------------------------------------------------------------------------- #
# retract_on_travel: insert a retraction before, and prime after, each travel
# --------------------------------------------------------------------------- #

def retract_on_travel(toolpath: Toolpath, min_distance: float = 2.0) -> Toolpath:
    '''Insert a Retraction before, and an Unretraction after, each travel move longer than
    min_distance that sits between two extruding moves - the classic anti-stringing pass.
    (The nearest segments are found by skipping any non-motion events in between.)'''
    from fullcontrol.gcode.extrusion_classes import Retraction, Unretraction
    events = toolpath.events

    def nearest_segment(indices):
        for j in indices:
            if isinstance(events[j], Segment):
                return events[j]
        return None

    out = []
    for i, ev in enumerate(events):
        if isinstance(ev, Segment) and ev.travel and ev.length > min_distance:
            prev_seg = nearest_segment(range(i - 1, -1, -1))
            next_seg = nearest_segment(range(i + 1, len(events)))
            if prev_seg is not None and not prev_seg.travel and next_seg is not None and not next_seg.travel:
                out.append(Retraction())
                out.append(ev)
                out.append(Unretraction())
                continue
        out.append(ev)
    return Toolpath(out)


register_pass('retract_on_travel', retract_on_travel)


# --------------------------------------------------------------------------- #
# coasting: stop extruding `distance` mm before the end of a run, to cut blobbing
# --------------------------------------------------------------------------- #

def _next_motion(events, i):
    'The next Segment after index i, skipping non-motion events; None if there is none.'
    for j in range(i + 1, len(events)):
        if isinstance(events[j], Segment):
            return events[j]
    return None


def coasting(toolpath: Toolpath, distance: float = 1.0) -> Toolpath:
    '''Turn the last `distance` mm of each extruding run into a non-extruding (coasting) move,
    so residual nozzle pressure - not fresh material - finishes the line. Splits the final
    extruding line move before a travel (or the end) `A->B` into `A->P` (extruding, material
    scaled to the shortened length) plus `P->B` (travel, no material). Arcs are left untouched.'''
    if distance <= 0:
        return toolpath
    events = toolpath.events
    out = []
    for i, ev in enumerate(events):
        if (isinstance(ev, Segment) and ev.kind == 'line' and not ev.travel
                and ev.length > distance):
            nxt = _next_motion(events, i)
            if nxt is None or nxt.travel:
                frac = (ev.length - distance) / ev.length
                p = tuple(None if ev.start[k] is None or ev.end[k] is None
                          else ev.start[k] + (ev.end[k] - ev.start[k]) * frac for k in range(3))
                out.append(Segment(ev.start, p, False, ev.speed, ev.length - distance,
                                   ev.deposited_volume * frac, ev.filament_length * frac,
                                   ev.source_index, kind='line', width=ev.width,
                                   height=ev.height, color=ev.color))
                out.append(Segment(p, ev.end, True, ev.speed, distance, 0.0, 0.0,
                                   ev.source_index, kind='line', width=ev.width,
                                   height=ev.height, color=ev.color))
                continue
        out.append(ev)
    return Toolpath(out)


register_pass('coasting', coasting)


# --------------------------------------------------------------------------- #
# z_hop: lift the nozzle by `height` for the duration of each travel move
# --------------------------------------------------------------------------- #

def z_hop(toolpath: Toolpath, height: float = 0.4) -> Toolpath:
    '''Raise every travel move by `height` in Z so the nozzle clears the print - the classic
    anti-collision / anti-stringing pass. Each travel line move `A->B` becomes three travel
    moves: a vertical lift, the travel at the raised Z, and a vertical lower back to B. Arcs,
    zero-length moves, and the initial positioning move (a None component) are left untouched.'''
    out = []
    for ev in toolpath.events:
        if (isinstance(ev, Segment) and ev.kind == 'line' and ev.travel and ev.length > 0
                and ev.start[2] is not None and ev.end[2] is not None
                and None not in ev.start and None not in ev.end):
            a, b = ev.start, ev.end
            a_up = (a[0], a[1], a[2] + height)
            b_up = (b[0], b[1], b[2] + height)
            out.append(Segment(a, a_up, True, ev.speed, height, 0.0, 0.0, ev.source_index,
                               kind='line', width=ev.width, height=ev.height, color=ev.color))
            out.append(Segment(a_up, b_up, True, ev.speed, ev.length, 0.0, 0.0, ev.source_index,
                               kind='line', width=ev.width, height=ev.height, color=ev.color))
            out.append(Segment(b_up, b, True, ev.speed, height, 0.0, 0.0, ev.source_index,
                               kind='line', width=ev.width, height=ev.height, color=ev.color))
        else:
            out.append(ev)
    return Toolpath(out)


register_pass('z_hop', z_hop)
