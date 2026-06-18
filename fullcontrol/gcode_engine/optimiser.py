"""The optimisation engine: run IR->IR passes with before/after simulation metrics.

``optimise_toolpath`` folds a list of pass specs (the same ``[name | (name, params)]`` format the
existing ``apply_passes``/``initialization_data['optimize']`` accept) over a Toolpath, simulating
before each pass and after it so every pass's effect on segment count, print time and deposited
volume is captured. The aggregate is an :class:`OptimisationReport` (one :class:`PassResult` per
pass) - the before/after pattern of ``examples/optimization_demo``'s ``optimization_report``,
lifted to structured data.
"""
from dataclasses import dataclass, field

from fullcontrol.ir.passes import apply_passes, get_pass
from fullcontrol.ir.toolpath import Segment, Toolpath
from fullcontrol.simulate.run import simulate_from_ir


def _segment_count(toolpath: Toolpath) -> int:
    return sum(1 for e in toolpath.events if isinstance(e, Segment))


@dataclass
class PassResult:
    'Per-pass before/after metrics from one optimisation pass.'
    name: str
    segments_before: int
    segments_after: int
    time_before_s: float
    time_after_s: float
    volume_before: float
    volume_after: float
    travel_before: float = 0.0
    travel_after: float = 0.0

    def summary(self) -> str:
        return (f'{self.name}: {self.segments_before}->{self.segments_after} segments, '
                f'time {self.time_before_s:.1f}->{self.time_after_s:.1f}s, '
                f'travel {self.travel_before:.1f}->{self.travel_after:.1f}mm, '
                f'volume {self.volume_before:.3f}->{self.volume_after:.3f}mm^3')


@dataclass
class OptimisationReport:
    '''Aggregate before/after report for an ``optimise_gcode`` run.

    ``passes`` is one :class:`PassResult` per applied pass (in order); the top-level
    before/after metrics span the whole pipeline.'''
    passes: list = field(default_factory=list)
    segments_before: int = 0
    segments_after: int = 0
    time_before_s: float = 0.0
    time_after_s: float = 0.0
    volume_before: float = 0.0
    volume_after: float = 0.0
    travel_before: float = 0.0
    travel_after: float = 0.0

    def summary(self) -> str:
        head = (f'optimise: {self.segments_before}->{self.segments_after} segments, '
                f'time {self.time_before_s:.1f}->{self.time_after_s:.1f}s, '
                f'travel {self.travel_before:.1f}->{self.travel_after:.1f}mm, '
                f'volume {self.volume_before:.3f}->{self.volume_after:.3f}mm^3')
        return '\n'.join([head] + ['  ' + p.summary() for p in self.passes])


def optimise_toolpath(toolpath: Toolpath, specs) -> tuple:
    '''Apply ``specs`` (a list of pass name | (name, params)) to ``toolpath`` one at a time,
    recording a :class:`PassResult` per pass. Returns ``(optimised_toolpath, OptimisationReport)``.'''
    report = OptimisationReport()
    sim0 = simulate_from_ir(toolpath)
    report.segments_before = _segment_count(toolpath)
    report.time_before_s = sim0.total_time_s
    report.volume_before = sim0.extruded_volume
    report.travel_before = sim0.travel_distance

    current = toolpath
    for spec in specs:
        name = spec if isinstance(spec, str) else spec[0]
        before = simulate_from_ir(current)
        seg_before = _segment_count(current)
        current = apply_passes(current, [spec])
        after = simulate_from_ir(current)
        report.passes.append(PassResult(
            name=name,
            segments_before=seg_before,
            segments_after=_segment_count(current),
            time_before_s=before.total_time_s,
            time_after_s=after.total_time_s,
            volume_before=before.extruded_volume,
            volume_after=after.extruded_volume,
            travel_before=before.travel_distance,
            travel_after=after.travel_distance,
        ))

    sim1 = simulate_from_ir(current)
    report.segments_after = _segment_count(current)
    report.time_after_s = sim1.total_time_s
    report.volume_after = sim1.extruded_volume
    report.travel_after = sim1.travel_distance
    return current, report


# the default, material-safe pass set when the caller passes passes=None (no aggressive geometry
# rewrites by default; simplify/arc_fit/travel_reorder conserve material, adaptive_speed only F)
DEFAULT_PASSES = ['simplify', 'arc_fit', 'travel_reorder']


def resolve_specs(passes):
    'Validate that every pass name in `passes` is registered (raises early with a clear error).'
    for spec in passes:
        name = spec if isinstance(spec, str) else spec[0]
        get_pass(name)  # raises ValueError on unknown
    return passes
