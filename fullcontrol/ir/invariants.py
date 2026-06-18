"""Check a Toolpath against the declared IR invariants - makes the v2 `invariants` header enforceable.

The v2 serialized IR (fullcontrol/ir/serialize.py) can DECLARE which invariants a toolpath is intended
to satisfy (the `INVARIANTS` vocabulary). This module ENFORCES them: `check_invariants(toolpath, names)`
folds the IR event stream and returns a structured report, so a declared invariant is a checkable
contract rather than decoration. The checks mirror the validate / verify_gcode rules but operate
directly on the IR (see docs/ir_spec.md section 3).

    from fullcontrol.ir import resolve, check_invariants
    tp = resolve(steps, controls)
    report = check_invariants(tp, ['monotonic_layer_z', 'within_build_volume'], build_volume=(200,200,200))
    report.raise_if_violated()

Some invariants need a parameter (`within_build_volume` -> build_volume; `bounded_flow` -> max_flow). If
the parameter is absent the invariant is reported `checked=False` (vacuously ok) rather than failing, so
declaring an invariant you can't yet check is safe.
"""
from dataclasses import dataclass, field

from fullcontrol.ir.serialize import INVARIANTS
from fullcontrol.ir.toolpath import Segment, MaterialEvent

_TOL = 1e-9


@dataclass
class InvariantResult:
    'The outcome of one invariant check. `violations` lists the offending event indices + detail.'
    name: str
    ok: bool
    checked: bool = True
    violations: list = field(default_factory=list)
    detail: str = ''


@dataclass
class InvariantReport:
    results: list

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def all_checked(self) -> bool:
        return all(r.checked for r in self.results)

    def summary(self) -> str:
        lines = []
        for r in self.results:
            if not r.checked:
                lines.append(f'- {r.name}: not checked ({r.detail})')
            elif r.ok:
                lines.append(f'- {r.name}: ok')
            else:
                lines.append(f'- {r.name}: VIOLATED ({len(r.violations)}) - {r.detail}')
        return '\n'.join(lines)

    def raise_if_violated(self):
        bad = [r for r in self.results if not r.ok]
        if bad:
            names = ', '.join(r.name for r in bad)
            raise ValueError(f'IR invariant(s) violated: {names}\n{self.summary()}')


def _extruding_segments(events):
    'Yield (index, segment) for extruding line/arc moves with a real length.'
    for i, ev in enumerate(events):
        if isinstance(ev, Segment) and not ev.travel:
            yield i, ev


def _non_negative_extrusion(events, **_):
    v = [{'index': i, 'deposited_volume': ev.deposited_volume}
         for i, ev in enumerate(events)
         if isinstance(ev, (Segment, MaterialEvent)) and ev.deposited_volume < -_TOL]
    return InvariantResult('non_negative_extrusion', not v, violations=v,
                           detail='a move/material deposits negative volume' if v else '')


def _monotonic_layer_z(events, **_):
    'z of successive EXTRUDING moves must be non-decreasing (travels/z-hops excluded).'
    v, running_max = [], None
    for i, ev in _extruding_segments(events):
        z = ev.end[2]
        if z is None:
            continue
        if running_max is not None and z < running_max - _TOL:
            v.append({'index': i, 'z': z, 'previous_max_z': running_max})
        running_max = z if running_max is None else max(running_max, z)
    return InvariantResult('monotonic_layer_z', not v, violations=v,
                           detail='extruding z steps downward' if v else '')


def _within_build_volume(events, build_volume=None, **_):
    if build_volume is None:
        return InvariantResult('within_build_volume', True, checked=False,
                               detail='no build_volume given')
    bx, by, bz = build_volume
    v = []
    for i, ev in enumerate(events):
        if not isinstance(ev, Segment):
            continue
        for tag, p in (('start', ev.start), ('end', ev.end)):
            x, y, z = p
            if (x is not None and not -_TOL <= x <= bx + _TOL) or \
               (y is not None and not -_TOL <= y <= by + _TOL) or \
               (z is not None and not -_TOL <= z <= bz + _TOL):
                v.append({'index': i, tag: [x, y, z]})
    return InvariantResult('within_build_volume', not v, violations=v,
                           detail=f'coordinates outside {build_volume}' if v else '')


def _bounded_flow(events, max_flow=None, **_):
    if max_flow is None:
        return InvariantResult('bounded_flow', True, checked=False, detail='no max_flow given')
    v = []
    for i, ev in _extruding_segments(events):
        if ev.length > _TOL and ev.speed:
            time_s = ev.length / ev.speed * 60.0          # speed is mm/min
            flow = ev.deposited_volume / time_s if time_s > 0 else 0.0
            if flow > max_flow + _TOL:
                v.append({'index': i, 'flow': flow})
    return InvariantResult('bounded_flow', not v, violations=v,
                           detail=f'volumetric flow exceeds {max_flow} mm^3/s' if v else '')


def _no_cold_extrusion(events, **_):
    'No extruding move may precede a Hotend event that commands a positive temperature.'
    hot = False
    v = []
    for i, ev in enumerate(events):
        if isinstance(ev, Segment):
            if not ev.travel and ev.deposited_volume > _TOL and not hot:
                v.append({'index': i})
        elif type(ev).__name__ in ('Hotend',) and getattr(ev, 'temp', None):
            hot = True
    return InvariantResult('no_cold_extrusion', not v, violations=v,
                           detail='extrusion before the hotend is heated' if v else '')


_CHECKERS = {
    'non_negative_extrusion': _non_negative_extrusion,
    'monotonic_layer_z': _monotonic_layer_z,
    'within_build_volume': _within_build_volume,
    'no_cold_extrusion': _no_cold_extrusion,
    'bounded_flow': _bounded_flow,
}


def check_invariants(toolpath, invariants, *, build_volume=None, max_flow=None) -> InvariantReport:
    '''Check `toolpath` against the named `invariants` (from the INVARIANTS vocabulary).

    Returns an InvariantReport (.ok / .all_checked / .summary() / .raise_if_violated()). Invariants
    needing a parameter that is not supplied are reported checked=False (vacuously ok). For the v2
    flow, pass the declared list: check_invariants(from_dict(d), d.get('invariants') or []).'''
    unknown = [n for n in invariants if n not in INVARIANTS]
    if unknown:
        raise ValueError(f'unknown invariant(s) {unknown} (recognised: {INVARIANTS})')
    results = [_CHECKERS[n](toolpath.events, build_volume=build_volume, max_flow=max_flow)
               for n in invariants]
    return InvariantReport(results)
