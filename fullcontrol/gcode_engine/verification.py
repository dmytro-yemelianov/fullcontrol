"""The verification report types: `Issue` and `VerificationReport`.

These are deliberately a *new* pair of plain dataclasses rather than an extension of the pydantic
`ValidationResult`. The verification engine ingests arbitrary g-code and emits richer issues than
the design-time validator: each `Issue` carries a `rule` name, a 1-based source-`line`, a
`segment_index`, and an optional `suggested_fix`. Reusing/extending `ValidationResult` would have
forced a breaking change to its pydantic schema; a superset dataclass keeps that schema stable
while giving the engine the provenance it needs.

`VerificationReport` mirrors `ValidationResult`'s public surface (`.errors`/`.warnings`/`.ok`/
`.summary()`/`.raise_if_errors()`) so callers can treat the two interchangeably, and additionally
exposes the `parse_params` used to lift the g-code and an optional inline `SimulationResult`.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Issue:
    '''A single verification finding.

    Attributes:
        severity: 'error' | 'warning' | 'info'.
        rule: the rule name that produced it (e.g. 'flow_rate_ceiling').
        message: a human-readable description.
        line: 1-based source g-code line number, or None when not tied to a line.
        segment_index: index of the offending Segment within the toolpath's Segment stream
            (0-based, in move order), or None.
        suggested_fix: an optional hint (e.g. an optimisation pass that would address it).
    '''
    severity: str
    rule: str
    message: str
    line: int | None = None
    segment_index: int | None = None
    suggested_fix: str | None = None

    def as_dict(self) -> dict:
        return {'severity': self.severity, 'rule': self.rule, 'message': self.message,
                'line': self.line, 'segment_index': self.segment_index,
                'suggested_fix': self.suggested_fix}


@dataclass
class VerificationReport:
    '''The result of `verify_gcode`: a list of `Issue`s, the `ParseParams` used, and an optional
    inline `SimulationResult`. Superset of `ValidationResult`'s public surface.'''
    issues: list = field(default_factory=list)
    parse_params: object = None
    simulation: object = None  # a SimulationResult, when simulate=True

    def add(self, severity: str, rule: str, message: str, line=None, segment_index=None,
            suggested_fix=None):
        self.issues.append(Issue(severity, rule, message, line, segment_index, suggested_fix))

    def extend(self, issues):
        self.issues.extend(issues)

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == 'error']

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == 'warning']

    @property
    def infos(self):
        return [i for i in self.issues if i.severity == 'info']

    @property
    def ok(self) -> bool:
        'True if there are no error-level issues.'
        return not self.errors

    def summary(self) -> str:
        lines = []
        if not self.issues:
            lines.append('verification passed: no issues found')
        else:
            for i in self.issues:
                loc = ''
                if i.line is not None:
                    loc += f' (line {i.line}'
                    if i.segment_index is not None:
                        loc += f', segment {i.segment_index}'
                    loc += ')'
                elif i.segment_index is not None:
                    loc += f' (segment {i.segment_index})'
                fix = f' [fix: {i.suggested_fix}]' if i.suggested_fix else ''
                lines.append(f'[{i.severity}] {i.rule}: {i.message}{loc}{fix}')
        if self.simulation is not None:
            lines.append(self.simulation.summary())
        return '\n'.join(lines)

    def raise_if_errors(self):
        if not self.ok:
            raise ValueError('g-code verification failed:\n'
                             + '\n'.join(f'{e.rule}: {e.message}' for e in self.errors))
