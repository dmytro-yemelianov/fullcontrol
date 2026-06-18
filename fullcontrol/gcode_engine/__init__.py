"""G-code verification & optimisation engine (Phase 1: parser + detector).

The engine ingests arbitrary g-code (our own output and other slicers') and lifts it back to the
same `Toolpath` IR that `resolve()` produces, so the existing passes/validators/simulators can
consume it unchanged. Phase 1 ships the pure-Python parser and its dialect detector; the
verification rules, optimisation passes, Rust parser and CLI are later phases.
"""
from fullcontrol.gcode_engine.detector import ParseParams
from fullcontrol.gcode_engine.parser import parse_gcode
from fullcontrol.gcode_engine.verification import Issue, VerificationReport
from fullcontrol.gcode_engine.public import verify_gcode, optimise_gcode
from fullcontrol.gcode_engine.optimiser import OptimisationReport, PassResult
from fullcontrol.gcode_engine import passes  # noqa: F401 - registers the Phase-4 optimisation passes

__all__ = ['parse_gcode', 'ParseParams', 'verify_gcode', 'VerificationReport', 'Issue',
           'optimise_gcode', 'OptimisationReport', 'PassResult']
