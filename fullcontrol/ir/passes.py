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
