"""Phase 0 in-place improvements (safety net + cleanups)."""
from types import SimpleNamespace

import pytest

import fullcontrol as fc


# I9 — shared gcode number-format helper
def test_fmt_matches_legacy_idiom_and_avoids_scientific_notation():
    from fullcontrol.gcode.number_format import fmt
    assert fmt(1.0) == '1'
    assert fmt(0.0) == '0'
    assert fmt(12.3456789) == '12.345679'
    assert fmt(1000000.5) == '1000000.5'
    assert fmt(0.00001) == '0.00001'          # would be '1e-05' with :.6 sig-figs
    assert fmt(1e-7).lower().find('e') == -1   # no scientific notation
    assert fmt(100.0, dp=1) == '100'           # feedrate-style 1-decimal


# I13 — GcodeComment must not IndexError when gcode output is still empty
def test_gcode_comment_empty_output_does_not_crash():
    state = SimpleNamespace(gcode=[])
    from fullcontrol.gcode.annotations import GcodeComment
    # previously raised IndexError on state.gcode[-1]
    result = GcodeComment(end_of_previous_line_text='note', text='hi').gcode(state)
    assert result == '; hi'
    assert state.gcode == []  # nothing to append to, silently skipped


# I10 — the processing loop should report which step failed
def test_step_loop_error_names_offending_step():
    class Boom:
        def gcode(self, state):
            raise ValueError('kaboom')
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
             fc.Point(x=1, y=1, z=0.2), Boom()]
    with pytest.raises(Exception) as exc:
        fc.transform(steps, 'gcode',
                     fc.GcodeControls(printer_name='generic'), show_tips=False)
    assert 'Boom' in str(exc.value)
