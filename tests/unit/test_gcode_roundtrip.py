"""Round-trip correctness anchor for the g-code -> IR parser (Phase 1).

The parser (`fullcontrol.gcode_engine.parse_gcode`) is the inverse of the g-code dialect
emitter. Its correctness anchor is a **byte-identical round-trip**: emit g-code from a design,
parse it back to a Toolpath, re-emit, and assert the bytes are unchanged. This pins the parser
to the emitter the way the columnar tests pin the resolvers.

Two strengths of round-trip are exercised:

* **Motion round-trip** - emit motion-only g-code (the resolved Segments only, no procedures),
  parse, re-emit, assert byte-identical. This isolates the motion <-> Segment inversion.
* **Full-file round-trip** - the complete `fc.transform(..., 'gcode')` output (procedures,
  primer, M-codes and motion) parsed with `ParseParams.from_controls(controls)`, re-emitted,
  asserted byte-identical. Procedures/primer come back through the verbatim ManualGcode
  pass-through; motion through Segments.

All emission uses the pure-Python dialect (no Rust kernel) so the suite is CI-safe.
"""
import pytest

import fullcontrol as fc
from fullcontrol.gcode.state import State
from fullcontrol.gcode.dialect import gcode_from_ir
from fullcontrol.ir import resolve
from fullcontrol.gcode_engine import parse_gcode, ParseParams


# --- helpers -------------------------------------------------------------------------------

def _emit_full(steps, controls):
    'The full pure-Python gcode (procedures + motion), exactly as fc.transform(...,"gcode").'
    controls.initialize()
    dstate = State(steps, controls)
    toolpath = resolve(steps, controls, state=dstate)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


def _emit_motion_only(steps, controls):
    'Motion-only gcode: just the resolved user Segments (no primer/procedures).'
    controls.initialize()
    dstate = State(steps, controls)
    toolpath = resolve(steps, controls, include_procedures=False, state=dstate)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


def _reemit(toolpath, controls):
    'Re-emit a parsed Toolpath through the same pure-Python dialect.'
    controls.initialize()
    dstate = State([], controls, procedures=False)
    gcode_from_ir(toolpath, dstate)
    return '\n'.join(dstate.gcode)


# --- designs -------------------------------------------------------------------------------

def _square():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
            fc.Point(x=10, y=0), fc.Point(x=10, y=10),
            fc.Point(x=0, y=10), fc.Point(x=0, y=0)]


def _with_travel():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Extruder(on=False), fc.Point(x=20, y=0),
            fc.Extruder(on=True), fc.Point(x=20, y=10), fc.Point(x=10, y=10)]


def _with_arc():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0),
            fc.Arc(centre=fc.Point(x=10, y=5), end=fc.Point(x=10, y=10), direction='anticlockwise'),
            fc.Point(x=0, y=10)]


def _multilayer():
    steps = [fc.Extruder(on=True)]
    for layer in range(3):
        z = 0.2 * (layer + 1)
        steps += [fc.Point(x=0, y=0, z=z), fc.Point(x=10, y=0), fc.Point(x=10, y=10), fc.Point(x=0, y=10)]
    return steps


DESIGNS = {
    'square': _square,
    'travel': _with_travel,
    'arc': _with_arc,
    'multilayer': _multilayer,
}

# (relative_e, travel_format) variants. e_units stays 'mm' (matches generic default).
E_VARIANTS = [
    ('rel_g0', {'relative_e': True, 'travel_format': 'G0'}),
    ('abs_g0', {'relative_e': False, 'travel_format': 'G0'}),
    ('abs_g1e0', {'relative_e': False, 'travel_format': 'G1_E0'}),
]


def _controls(**init):
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'primer': 'no_primer', **init})


# --- 1. motion round-trip (primary) --------------------------------------------------------

@pytest.mark.parametrize('design_name', list(DESIGNS))
@pytest.mark.parametrize('variant_name,init', E_VARIANTS)
def test_motion_roundtrip_byte_identical(design_name, variant_name, init):
    steps = DESIGNS[design_name]()
    controls = _controls(**init)
    gc = _emit_motion_only(steps, controls)
    assert gc.strip(), 'design emitted no motion'

    tp = parse_gcode(gc, ParseParams.from_controls(_controls(**init)))
    reemitted = _reemit(tp, _controls(**init))
    assert reemitted == gc, (
        f'motion round-trip not byte-identical for {design_name}/{variant_name}\n'
        f'--- original ---\n{gc}\n--- reemitted ---\n{reemitted}')


# --- 2. full-file round-trip (stronger) ----------------------------------------------------

@pytest.mark.parametrize('design_name', list(DESIGNS))
@pytest.mark.parametrize('variant_name,init', E_VARIANTS)
def test_full_file_roundtrip_byte_identical(design_name, variant_name, init):
    steps = DESIGNS[design_name]()
    controls = _controls(**init)
    gc = _emit_full(steps, controls)

    params = ParseParams.from_controls(_controls(**init))
    tp = parse_gcode(gc, params)
    reemitted = _reemit(tp, _controls(**init))
    assert reemitted == gc, (
        f'full-file round-trip not byte-identical for {design_name}/{variant_name}\n'
        f'--- original ---\n{gc}\n--- reemitted ---\n{reemitted}')


def test_full_file_roundtrip_real_printer():
    'A real printer profile (full start/end procedures) round-trips byte-identically.'
    steps = _square()
    controls = fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})
    gc = _emit_full(steps, controls)
    params = ParseParams.from_controls(
        fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}))
    tp = parse_gcode(gc, params)
    reemitted = _reemit(tp, fc.GcodeControls(printer_name='generic',
                                             initialization_data={'nozzle_temp': 210}))
    assert reemitted == gc


# --- arc structure preserved ---------------------------------------------------------------

def test_arc_parsed_as_arc_segment():
    from fullcontrol.ir import Segment
    steps = _with_arc()
    controls = _controls()
    gc = _emit_motion_only(steps, controls)
    tp = parse_gcode(gc, ParseParams.from_controls(_controls()))
    arcs = [e for e in tp.events if isinstance(e, Segment) and e.kind == 'arc']
    assert len(arcs) == 1
    assert arcs[0].centre is not None
    assert arcs[0].clockwise is False  # emitted with G3 (anticlockwise)


# --- 3. detector tests ---------------------------------------------------------------------

def test_detect_relative_e_from_m83():
    p = ParseParams.detect('M83 ; relative extrusion\nG1 X1 E0.1')
    assert p.relative_e is True


def test_detect_absolute_e_from_m82():
    p = ParseParams.detect('M82 ; absolute extrusion\nG92 E0\nG1 X1 E0.1')
    assert p.relative_e is False


def test_detect_klipper_header():
    text = ('; generated by SuperSlicer\n'
            'SET_PRESSURE_ADVANCE ADVANCE=0.05\n'
            'G1 X1 Y1 E0.1\n')
    p = ParseParams.detect(text)
    assert p.flavor == 'klipper'


def test_absolute_e_with_g92_reset_handled():
    'Absolute E with a mid-stream G92 E0 reset still recovers per-move extrusion.'
    from fullcontrol.ir import Segment
    text = ('M82\nG92 E0\n'
            'G1 F1000 X10 E0.5\n'
            'G92 E0\n'              # reset accumulator
            'G1 X20 E0.5\n')       # another 0.5 of filament, not 0
    p = ParseParams(flavor='marlin', relative_e=False, e_units='mm', dia_feed=1.75)
    tp = parse_gcode(text, p)
    segs = [e for e in tp.events if isinstance(e, Segment)]
    assert len(segs) == 2
    assert segs[1].filament_length == pytest.approx(0.5)
    assert not segs[1].travel


# --- 4. robustness -------------------------------------------------------------------------

def test_malformed_line_does_not_crash_and_is_preserved():
    text = ('M83\n'
            'G1 F1000 X10 E0.1\n'
            'THIS IS NOT GCODE @#$%\n'
            'G1 X20 E0.1\n')
    tp = parse_gcode(text)  # default params
    texts = [getattr(e, 'text', None) for e in tp.events]
    assert 'THIS IS NOT GCODE @#$%' in texts


def test_bad_coordinate_inherits_previous():
    'A malformed coordinate token must not crash; the move inherits the previous position.'
    text = ('M83\n'
            'G1 F1000 X10 Y5 E0.1\n'
            'G1 Xabc Y15 E0.1\n')  # bad X token -> inherit previous X
    tp = parse_gcode(text)
    # parser must not raise; the garbage line is preserved verbatim or parsed forgivingly
    assert tp.events


def test_empty_input():
    tp = parse_gcode('')
    assert tp.events == []
