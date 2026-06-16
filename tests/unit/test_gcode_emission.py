"""Characterization tests for FullControl gcode emission.

These tests lock down the *observable* gcode-string behaviour produced by
``fc.transform(steps, 'gcode', ...)`` so that future refactors (e.g. separating
the renderer from the state machine) can be verified to preserve behaviour.

They assert on substrings / line counts / regexes within the full gcode string,
so they are robust to the surrounding start/end procedure and primer lines that
the 'generic' printer injects.

Key facts about the 'generic' printer (verified against current code):
  * primer is 'travel': it emits ``Extruder(on=False)``, a travel move to the
    first user point, then ``Extruder(on=True)``. So the first user point is a
    G0 travel move and subsequent moves are G1 extruding moves.
  * default ``relative_e`` is True -> start gcode contains ``M83``.
  * default print_speed=1000, travel_speed=8000.
"""

import re

import fullcontrol as fc
from fullcontrol.gcode.number_format import fmt


def emit(steps, **init):
    """Transform ``steps`` to a gcode string using the generic printer."""
    controls = fc.GcodeControls(printer_name='generic', initialization_data=init)
    return fc.transform(steps, 'gcode', controls, show_tips=False)


def move_lines(gcode):
    """Return only the G0/G1 motion/extrusion lines from a gcode string."""
    return [ln for ln in gcode.splitlines() if ln.startswith(('G0 ', 'G1 '))]


# ---------------------------------------------------------------------------
# Travel vs extruding moves
# ---------------------------------------------------------------------------

def test_travel_move_emits_g0_with_no_e():
    # The primer travels (extruder off) to the first user point -> G0, no E.
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0)])
    moves = move_lines(gcode)
    first_travel = moves[0]
    assert first_travel.startswith('G0 ')
    assert 'E' not in first_travel


def test_extruding_move_emits_g1_with_e_value():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0)])
    moves = move_lines(gcode)
    # second move is the extruding move to (10,0,0)
    extruding = moves[1]
    assert extruding.startswith('G1 ')
    assert re.search(r'\bE\d', extruding), f'no E value in {extruding!r}'


# ---------------------------------------------------------------------------
# Coordinate formatting (no scientific notation) - the fmt contract
# ---------------------------------------------------------------------------

def test_large_coordinate_not_scientific():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=1000000.5, y=0, z=0)])
    assert 'X1000000.5' in gcode
    # ensure no exponent leaked into any axis/extrusion field
    for ln in move_lines(gcode):
        for field in ln.split():
            assert 'e' not in field[1:].lower(), f'scientific notation in {field!r}'


def test_small_coordinate_not_scientific():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=0.00001, y=0, z=0)])
    assert 'X0.00001' in gcode
    assert '1e-05' not in gcode and '1E-05' not in gcode


def test_fmt_helper_strips_trailing_zeros_and_point():
    # the contract relied on by every coordinate/extrusion field
    assert fmt(1.0) == '1'
    assert fmt(1000000.5) == '1000000.5'
    assert fmt(0.00001) == '0.00001'
    assert 'e' not in fmt(1234567.0).lower()


# ---------------------------------------------------------------------------
# Only-changed axes are emitted
# ---------------------------------------------------------------------------

def test_only_changed_axis_emitted():
    # move from (0,0,0) changing only x -> X present, Y and Z absent
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=5)])
    moves = move_lines(gcode)
    x_only = moves[1]
    assert 'X5' in x_only
    assert 'Y' not in x_only
    assert 'Z' not in x_only


def test_all_three_axes_emitted_on_first_move():
    # first move sets X, Y and Z (all differ from the default origin point)
    gcode = emit([fc.Point(x=1, y=2, z=3), fc.Point(x=1, y=2, z=3)])
    moves = move_lines(gcode)
    first = moves[0]
    assert 'X1' in first and 'Y2' in first and 'Z3' in first


# ---------------------------------------------------------------------------
# Feedrate (F) emission
# ---------------------------------------------------------------------------

def test_feedrate_emitted_on_first_move():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10)])
    first = move_lines(gcode)[0]
    assert re.search(r'\bF\d', first), f'no feedrate on first move: {first!r}'


def test_feedrate_changes_between_travel_and_print_speed():
    # travel move uses travel_speed (8000), print move uses print_speed (1000)
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0)])
    moves = move_lines(gcode)
    assert 'F8000' in moves[0]  # travel
    assert 'F1000' in moves[1]  # print


def test_feedrate_not_repeated_when_unchanged():
    # three consecutive extruding moves at the same speed: F only on the first
    gcode = emit([
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=5), fc.Point(x=10), fc.Point(x=15),
    ])
    moves = move_lines(gcode)
    extruding = moves[1:]  # moves[0] is the travel primer move
    assert 'F1000' in extruding[0]
    assert 'F' not in extruding[1]
    assert 'F' not in extruding[2]


# ---------------------------------------------------------------------------
# Extruder on/off toggling
# ---------------------------------------------------------------------------

def test_extruder_off_then_on_toggles_g0_g1_and_e():
    gcode = emit([
        fc.Point(x=0, y=0, z=0),
        fc.Extruder(on=False), fc.Point(x=10, y=0, z=0),
        fc.Extruder(on=True), fc.Point(x=10, y=10, z=0),
    ])
    moves = move_lines(gcode)
    # find the explicit-off travel move to (10,0,0) and the on move to (10,10,0)
    off_move = next(ln for ln in moves if 'X10' in ln and 'Y' not in ln)
    on_move = next(ln for ln in moves if 'Y10' in ln)
    assert off_move.startswith('G0 ')
    assert 'E' not in off_move
    assert on_move.startswith('G1 ')
    assert re.search(r'\bE\d', on_move)


# ---------------------------------------------------------------------------
# Relative vs absolute extrusion start gcode
# ---------------------------------------------------------------------------

def test_relative_extrusion_emits_m83():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10)], relative_e=True)
    assert 'M83' in gcode
    assert 'M82' not in gcode


def test_absolute_extrusion_emits_m82_and_g92():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Point(x=10)], relative_e=False)
    assert 'M82' in gcode
    assert 'G92 E0' in gcode
    assert 'M83' not in gcode


# ---------------------------------------------------------------------------
# Fan
# ---------------------------------------------------------------------------

def test_fan_50_percent_emits_m106_s127():
    # int(50*255/100) == 127
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Fan(speed_percent=50)])
    assert 'M106 S127' in gcode


def test_fan_0_percent_emits_m106_s0():
    # current code emits M106 S0 (not M107) for zero speed
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Fan(speed_percent=0)])
    assert 'M106 S0' in gcode
    assert 'M107' not in gcode


# ---------------------------------------------------------------------------
# Hotend / Buildplate temperature commands
# ---------------------------------------------------------------------------

def test_hotend_wait_emits_m109():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Hotend(temp=210, wait=True)])
    assert 'M109 S210' in gcode


def test_hotend_no_wait_emits_m104():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Hotend(temp=210, wait=False)])
    assert 'M104 S210' in gcode


def test_buildplate_wait_emits_m190():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Buildplate(temp=60, wait=True)])
    assert 'M190 S60' in gcode


def test_buildplate_no_wait_emits_m140():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.Buildplate(temp=60, wait=False)])
    assert 'M140 S60' in gcode


# ---------------------------------------------------------------------------
# ManualGcode / GcodeComment
# ---------------------------------------------------------------------------

def test_manual_gcode_emits_literal_line():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.ManualGcode(text='SOME_LITERAL_LINE')])
    assert 'SOME_LITERAL_LINE' in gcode.splitlines()


def test_gcode_comment_prefixes_semicolon():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.GcodeComment(text='hello world')])
    assert '; hello world' in gcode.splitlines()


# ---------------------------------------------------------------------------
# StationaryExtrusion
# ---------------------------------------------------------------------------

def test_stationary_extrusion_line_format_and_no_scientific():
    gcode = emit([fc.Point(x=0, y=0, z=0), fc.StationaryExtrusion(volume=0.00001, speed=1000)])
    line = next(ln for ln in gcode.splitlines()
                if ln.startswith('G1 F') and 'E' in ln and 'X' not in ln)
    assert re.match(r'^G1 F1000 E[\d.]+$', line), f'unexpected stationary line: {line!r}'
    e_field = line.split()[-1]
    assert 'e' not in e_field[1:].lower(), f'scientific notation in {e_field!r}'


# ---------------------------------------------------------------------------
# A simple square design
# ---------------------------------------------------------------------------

def test_simple_square_produces_expected_move_sequence():
    square = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Point(x=10, y=10, z=0),
        fc.Point(x=0, y=10, z=0),
        fc.Point(x=0, y=0, z=0),
    ]
    gcode = emit(square)
    moves = move_lines(gcode)
    # primer travel to (0,0,0) is G0; the 4 edges are G1 extruding moves
    assert moves[0].startswith('G0 ')
    extruding = [ln for ln in moves if ln.startswith('G1 ')]
    assert len(extruding) == 4, f'expected 4 extruding edges, got {len(extruding)}: {extruding}'
    # each edge should carry an extrusion amount
    for edge in extruding:
        assert re.search(r'\bE\d', edge), f'edge missing extrusion: {edge!r}'
    # the four edges trace the square in order
    assert 'X10' in extruding[0] and 'Y' not in extruding[0]      # ->(10,0)
    assert 'Y10' in extruding[1] and 'X' not in extruding[1]      # ->(10,10)
    assert 'X0' in extruding[2] and 'Y' not in extruding[2]       # ->(0,10)
    assert 'Y0' in extruding[3] and 'X' not in extruding[3]       # ->(0,0)


# ---------------------------------------------------------------------------
# save_as file output (uses tmp_path, no date suffix)
# ---------------------------------------------------------------------------

def test_save_as_writes_file(tmp_path):
    target = tmp_path / 'out'
    controls = fc.GcodeControls(
        printer_name='generic',
        initialization_data={},
        save_as=str(target),
        include_date=False,
    )
    gcode = fc.transform([fc.Point(x=0, y=0, z=0), fc.Point(x=10)], 'gcode', controls, show_tips=False)
    written = (tmp_path / 'out.gcode').read_text()
    assert written == gcode
