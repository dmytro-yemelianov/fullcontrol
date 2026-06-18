"""G-code verification & optimisation engine (Phase 1: parser + detector).

The engine ingests arbitrary g-code (our own output and other slicers') and lifts it back to the
same `Toolpath` IR that `resolve()` produces, so the existing passes/validators/simulators can
consume it unchanged. Phase 1 ships the pure-Python parser and its dialect detector; the
verification rules, optimisation passes, Rust parser and CLI are later phases.
"""
from fullcontrol.gcode_engine.detector import ParseParams
from fullcontrol.gcode_engine.parser import parse_gcode
from fullcontrol.gcode_engine.verification import Issue, VerificationReport
from fullcontrol.gcode_engine.public import verify_gcode

__all__ = ['parse_gcode', 'ParseParams', 'verify_gcode', 'VerificationReport', 'Issue']
