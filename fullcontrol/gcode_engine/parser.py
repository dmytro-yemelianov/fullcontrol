"""g-code -> Toolpath IR parser (the inverse of `fullcontrol/gcode/dialect.py`).

A stateful single-pass line scanner that holds the same running context as `resolve()` / the
dialect: a position cursor, the extruder on/off state, the running speed, an E accumulator and
the volume<->E ratio. Each line is stripped of its comment, tokenised (G/X/Y/Z/E/F/I/J/R) and
dispatched:

* ``G0`` -> travel ``Segment``; ``G1`` -> extruding/travel by the sign of dE; ``G2``/``G3`` ->
  arc ``Segment`` (centre = start + I/J, clockwise for G2), arc length/points via the existing
  ``fullcontrol.core.arc`` helpers (reused, not reinvented).
* ``G92 E0`` resets the E accumulator (no segment). ``G90``/``G91`` set absolute/relative XYZ.
* recognised non-motion lines pass through verbatim as ``ManualGcode`` so re-emission is
  byte-for-byte identical; unknown / comment / blank lines likewise.

The parser is the foundation of the verification/optimisation engine: it lifts arbitrary g-code
(our own and other slicers') back to the same `Toolpath` IR that `resolve()` produces, so every
existing pass, validator and simulator consumes it unchanged.

**Round-trip discipline.** To make ``emit(parse(g)) == g`` byte-identical, the parser inserts
the small pass-through *control events* the dialect needs to reproduce the feedrate (``F``) word
exactly: the dialect emits ``F`` only when its ``speed_changed`` flag is set, and clears it after
every motion line. So the parser inserts an ``Extruder(on=...)`` event whenever the extruder
toggles (the dialect sets ``speed_changed`` on a toggle) and a ``Printer(...)`` speed event
whenever the original line carried an ``F`` word without a toggle - reproducing the emitter's
feedrate-suppression precisely.

**Lossiness (documented).** ``width``/``height`` cannot be recovered from E alone (one equation,
two unknowns) -> ``None`` unless slicer ``;WIDTH:``/``;HEIGHT:`` comments supply them. ``color``
is always ``None``. ``arc_points`` are rebuilt from centre/clockwise. ``source_index`` is the
1-based g-code line number (provenance). The parser never raises on malformed input: an
unparseable line becomes a verbatim ``ManualGcode``; a bad coordinate token inherits the previous
value.
"""
from math import pi

from fullcontrol.core.arc import Arc, arc_geometry, arc_points
from fullcontrol.core.point import Point
from fullcontrol.ir import Segment, Toolpath
from fullcontrol.gcode.commands import ManualGcode
from fullcontrol.gcode.extrusion_classes import Extruder
from fullcontrol.gcode.printer import Printer
from fullcontrol.gcode_engine.detector import ParseParams

# arc tessellation segment count - matches the emitter's default Arc.segments so rebuilt
# arc_points have the same shape as resolve() produced.
_ARC_SEGMENTS = 100


def _volume_to_e(params: ParseParams) -> float:
    'Mirror ExtruderState.update_e_ratio: mm3 -> 1, mm -> 1/(pi r^2).'
    if params.e_units == 'mm3':
        return 1.0
    return 1.0 / (pi * (params.dia_feed / 2) ** 2)


def _tokenise(code: str) -> dict:
    '''Split a command word-list into {letter: float}. Robust to malformed tokens: a token
    whose value does not parse is skipped (the caller inherits the previous value).'''
    words = {}
    for tok in code.split():
        if not tok:
            continue
        letter = tok[0].upper()
        rest = tok[1:]
        if letter in 'GXYZEFIJRS':
            try:
                words[letter] = float(rest)
            except ValueError:
                continue  # malformed value -> skip; caller inherits previous
    return words


def _strip_comment(line: str):
    'Return (code, had_comment). Everything after the first ; is a comment.'
    idx = line.find(';')
    if idx == -1:
        return line.strip(), False
    return line[:idx].strip(), True


class _Cursor:
    'The running parse context (the mirror of resolve()/the dialect emission state).'

    def __init__(self, params: ParseParams):
        from fullcontrol.gcode.flavor import get_flavor
        self.params = params
        self.flavor = get_flavor(params.flavor)
        # the exact extrusion-mode text the dialect emits, for matching our own output so the
        # mode line(s) can be re-emitted from a real Extruder(relative_gcode=...) step (which
        # also drives the E-math state) rather than a verbatim ManualGcode (which would not).
        self._mode_rel = self.flavor.extrusion_mode(True)    # 'M83 ; relative extrusion'
        self._mode_abs = self.flavor.extrusion_mode(False)   # 'M82 ...\nG92 E0 ...'
        self.volume_to_e = _volume_to_e(params)
        self.x = self.y = self.z = None
        self.relative_xyz = False          # G90 (abs) default; G91 -> relative
        # E mode is driven by the M82/M83 lines actually present in the stream, not by the
        # params flag: the emitter emits absolute-cumulative E until an M83 appears (then
        # per-move relative). Motion-only output has no M-code -> absolute. So default abs.
        self.relative_e = False
        self.e_total = 0.0                 # cumulative E in gcode units (since last G92 reset)
        self.on = False                    # extruder on/off
        self.print_speed = None
        self.travel_speed = None
        self.cur_speed = None              # last F seen (mm/min)
        self.width = None                  # from ;WIDTH: comments, if present
        self.height = None


def parse_gcode(text: str, params: ParseParams = None) -> Toolpath:
    '''Parse g-code text into a Toolpath IR (the inverse of the dialect emitter).

    Args:
        text: the g-code as a single string (lines separated by ``\\n``).
        params: a `ParseParams` giving the flavor / E-mode / units / diameter context. When
            omitted, it is detected from the text via `ParseParams.detect`.

    Returns:
        A `Toolpath` whose events are `Segment`s for motion plus pass-through step events
        (`ManualGcode` for verbatim non-motion lines, and the control events that let the
        dialect re-emit feedrate words identically).

    Never raises on malformed input: an unparseable line becomes a verbatim `ManualGcode`; a
    bad coordinate token inherits the previous value.
    '''
    if params is None:
        params = ParseParams.detect(text)
    cur = _Cursor(params)
    events = []
    if text == '':
        return Toolpath(events)

    lines = text.split('\n')  # split (not splitlines) preserves exact line structure
    i = 0
    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        try:
            consumed = _parse_line(raw, lineno, cur, events, lines, i)
        except Exception:
            # absolute safety net: never panic - preserve the line verbatim
            events.append(ManualGcode(text=raw))
            consumed = 1
        i += consumed

    return Toolpath(events)


def _parse_line(raw: str, lineno: int, cur: _Cursor, events: list, lines: list, idx: int) -> int:
    '''Dispatch one g-code line. Returns the number of source lines consumed (usually 1; the
    absolute-mode "M82\\nG92 E0" two-line block consumes 2).'''
    code, had_comment = _strip_comment(raw)

    # blank / comment-only / unrecognised -> verbatim pass-through (byte-identical re-emit).
    # also pick up slicer width/height hints from comments for richer Segments.
    if not code:
        _scan_comment_hints(raw, cur)
        events.append(ManualGcode(text=raw))
        return 1

    head = code.split()[0].upper()

    if head in ('G0', 'G00', 'G1', 'G01', 'G2', 'G02', 'G3', 'G03'):
        # only parse a motion line into a Segment when it matches the dialect's own canonical
        # layout (F-first, no trailing comment); otherwise it is hand-written procedure g-code
        # (e.g. 'G0 Z20 F8000 ; drop bed' from a printer's end_gcode) that must round-trip
        # verbatim. The position cursor is deliberately NOT advanced here: the FullControl
        # resolver likewise never reads motion state from a ManualGcode text block, so the first
        # real Segment after the start g-code is emitted relative to the same initial cursor.
        has_f = any(t[:1].upper() == 'F' for t in code.split()[1:])
        no_speed_yet = not has_f and cur.cur_speed is None
        # FullControl motion lines are built with .strip() (no surrounding/padding whitespace);
        # any deviation marks hand-written g-code -> verbatim.
        not_tight = raw != raw.strip() or '  ' in code
        if had_comment or not_tight or not _is_canonical_motion(head, code) or no_speed_yet:
            # a motion line carrying no feedrate before any F has ever been seen is hand-written
            # procedure g-code (e.g. 'G0 Z0.2' in start g-code): the dialect's first emitted move
            # always carries an F. Preserve it verbatim.
            events.append(ManualGcode(text=raw))
            return 1

    if head in ('G0', 'G00', 'G1', 'G01'):
        _handle_linear(raw, code, lineno, cur, events)
    elif head in ('G2', 'G02', 'G3', 'G03'):
        _handle_arc(raw, code, lineno, cur, events, clockwise=head in ('G2', 'G02'))
    elif head == 'G92':
        _handle_g92(raw, code, cur, events)
    elif head in ('G90',):
        cur.relative_xyz = False
        events.append(ManualGcode(text=raw))
    elif head in ('M82', 'M83'):
        return _handle_extrusion_mode(raw, head, cur, events, lines, idx)
    else:
        # any other M-code / G-code / firmware command: preserved verbatim so it round-trips.
        events.append(ManualGcode(text=raw))
    return 1


def _handle_extrusion_mode(raw, head, cur, events, lines, idx) -> int:
    '''M82/M83 set the E mode. When the line (or the M82 + following G92 E0 block) matches the
    dialect's own extrusion_mode output exactly, emit it from a real Extruder(relative_gcode=...)
    step so the re-emit dialect's E-math (the relative_gcode ref reset) is reproduced and the
    text comes back byte-identical. Otherwise (external slicer with different/absent comment),
    keep the line verbatim - the E mode is still tracked for parsing, but byte-round-trip of the
    mode line is not guaranteed (documented external-file lossiness).'''
    if head == 'M83':
        cur.relative_e = True
        if raw == cur._mode_rel:
            events.append(Extruder(relative_gcode=True))
            cur.e_total = 0.0
            return 1
        events.append(ManualGcode(text=raw))
        return 1
    # head == 'M82'
    cur.relative_e = False
    # the dialect emits absolute mode as a two-line block 'M82 ...\nG92 E0 ...'.
    block = cur._mode_abs.split('\n')
    if len(block) == 2 and raw == block[0] and idx + 1 < len(lines) and lines[idx + 1] == block[1]:
        events.append(Extruder(relative_gcode=False))  # re-emits both lines, resets E ref
        cur.e_total = 0.0
        return 2  # consumed the M82 line and the following G92 E0 line
    events.append(ManualGcode(text=raw))
    return 1


# the dialect emits motion words in this fixed order: [F] X Y Z [I J] E. A line matching this
# order (and using only these letters) is FullControl-emitted motion we can reconstruct; anything
# else is hand-written and is preserved verbatim.
_CANONICAL_ORDER = ('F', 'X', 'Y', 'Z', 'I', 'J', 'E')


def _is_canonical_motion(head: str, code: str) -> bool:
    '''True iff the line is a FullControl-emitted motion line we can reconstruct byte-identically.

    The dialect emits motion words in a fixed order ([F] X Y Z [I J] E, using only those letters)
    and follows strict shape rules that distinguish emitted motion from hand-written procedure
    g-code: every emitted move carries at least one X/Y/Z axis; an emitted G1 always carries an E
    word (a no-E travel is emitted as G0, or as G1...E0 under the G1_E0 format); an emitted G0
    never carries E; an emitted arc carries I and J. Lines failing any of these are hand-written
    (e.g. ``G1 F840`` or ``G1 Z2`` in Cura start/end g-code) and are preserved verbatim.
    '''
    toks = code.split()[1:]  # drop the G-word
    rank = -1
    letters = set()
    for tok in toks:
        letter = tok[0].upper()
        if letter not in _CANONICAL_ORDER:
            return False
        r = _CANONICAL_ORDER.index(letter)
        if r <= rank:  # out of order or duplicate letter -> not canonical
            return False
        rank = r
        letters.add(letter)
        try:
            float(tok[1:])
        except ValueError:
            return False
    has_axis = bool(letters & {'X', 'Y', 'Z'})
    if not has_axis:
        return False
    if head in ('G2', 'G02', 'G3', 'G03'):
        return 'I' in letters and 'J' in letters
    if 'I' in letters or 'J' in letters:  # I/J on a linear move -> not our output
        return False
    if head in ('G1', 'G01'):
        return 'E' in letters       # an emitted G1 always carries E
    return 'E' not in letters       # an emitted G0 never carries E


def _scan_comment_hints(raw: str, cur: _Cursor) -> None:
    'Extract ;WIDTH:/;HEIGHT: hints (Prusa/Cura/Bambu) for width/height on following segments.'
    low = raw.lower()
    if ';width:' in low:
        cur.width = _num_after(low, ';width:') or cur.width
    if ';height:' in low or ';layer_height:' in low:
        key = ';height:' if ';height:' in low else ';layer_height:'
        cur.height = _num_after(low, key) or cur.height


def _num_after(s: str, key: str):
    import re
    seg = s.split(key, 1)[1]
    m = re.search(r'(-?\d+\.?\d*)', seg)
    return float(m.group(1)) if m else None


def _resolve_xyz(words: dict, cur: _Cursor):
    'Apply X/Y/Z words to the cursor (absolute or relative), returning (start, end).'
    sx, sy, sz = cur.x, cur.y, cur.z
    if cur.relative_xyz:
        ex = sx if 'X' not in words else (0.0 if sx is None else sx) + words['X']
        ey = sy if 'Y' not in words else (0.0 if sy is None else sy) + words['Y']
        ez = sz if 'Z' not in words else (0.0 if sz is None else sz) + words['Z']
    else:
        ex = sx if 'X' not in words else words['X']
        ey = sy if 'Y' not in words else words['Y']
        ez = sz if 'Z' not in words else words['Z']
    return (sx, sy, sz), (ex, ey, ez)


def _delta_e(words: dict, cur: _Cursor) -> float:
    'The E delta (gcode units) for this move, updating the accumulator. 0 if no E word.'
    if 'E' not in words:
        return 0.0
    e = words['E']
    if cur.relative_e:
        cur.e_total += e
        return e
    delta = e - cur.e_total
    cur.e_total = e
    return delta


def _length(start, end) -> float:
    'Euclidean length, ignoring an axis undefined in either endpoint (matches resolve()).'
    dx = 0.0 if start[0] is None or end[0] is None else end[0] - start[0]
    dy = 0.0 if start[1] is None or end[1] is None else end[1] - start[1]
    dz = 0.0 if start[2] is None or end[2] is None else end[2] - start[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _emit_speed_control(words: dict, cur: _Cursor, on: bool, events: list) -> float:
    '''Reproduce the dialect's feedrate (F) word exactly on re-emit.

    The dialect emits F iff its `speed_changed` flag is set, then clears it after each motion
    line. The original F pattern is therefore exactly "the lines that carried an F word". So we
    force `speed_changed` on re-emit precisely when the original line had an F word, by inserting
    a `Printer` speed event - and we set both print_speed and travel_speed to that F value, so
    the dialect emits the right number whichever mode (on/off) it reads. When the original line
    had no F word, we insert nothing, so the re-emit suppresses F identically.
    '''
    cur.on = on
    if 'F' not in words:
        return cur.cur_speed if cur.cur_speed is not None else 0.0
    speed = words['F']
    cur.cur_speed = speed
    # both speeds = this line's F so the dialect's f_gcode prints the right value regardless of
    # whether it reads print_speed (on) or travel_speed (off).
    events.append(Printer(print_speed=speed, travel_speed=speed))
    return speed


def _handle_linear(raw, code, lineno, cur, events):
    words = _tokenise(code)
    head = code.split()[0].upper()
    delta_e = _delta_e(words, cur)
    # travel vs extrude (mirrors the dialect's linear_move): G0 is always travel; a G1 is an
    # extruding move (the dialect emits G1 for extruding moves, including zero-extrusion ones
    # like the first positioning move). The exception is the 'G1_E0' travel format, where a
    # travel is itself emitted as a G1 carrying a no-op E word (dE == 0) - so under that format a
    # G1 with dE == 0 is a travel.
    if head in ('G0', 'G00'):
        on = False
    elif cur.params.travel_g1_e0 and delta_e == 0:
        # G1_E0 travel format: a travel is emitted as a G1 carrying a no-op E word (dE == 0),
        # but so is a zero-volume *extruding* move (e.g. the first positioning move). They are
        # indistinguishable from E alone, so inherit the previous on-state rather than force a
        # toggle - which keeps the feedrate (F) word suppression byte-identical. When delta == 0
        # the travel flag does not change the emitted E either, so the bytes match regardless.
        on = cur.on
    else:
        on = True
    start, end = _resolve_xyz(words, cur)

    speed = _emit_speed_control(words, cur, on, events)

    length = _length(start, end)
    deposited_volume = delta_e / cur.volume_to_e if cur.volume_to_e else 0.0
    filament_length = delta_e  # IR filament_length == vol * volume_to_e == the E value
    events.append(Segment(
        start=start, end=end, travel=not on, speed=speed, length=length,
        deposited_volume=deposited_volume, filament_length=filament_length,
        source_index=lineno, kind='line', width=cur.width, height=cur.height))
    cur.x, cur.y, cur.z = end


def _handle_arc(raw, code, lineno, cur, events, clockwise):
    words = _tokenise(code)
    if cur.x is None or cur.y is None or 'I' not in words or 'J' not in words:
        # cannot resolve an arc without a start position + I/J centre offsets -> preserve verbatim
        events.append(ManualGcode(text=raw))
        return
    delta_e = _delta_e(words, cur)
    on = delta_e > 0
    start, end = _resolve_xyz(words, cur)
    cx = cur.x + words['I']
    cy = cur.y + words['J']
    ez = end[2]

    # reuse the existing arc geometry/tessellation helpers (do not reinvent)
    direction = 'clockwise' if clockwise else 'anticlockwise'
    arc = Arc(centre=Point(x=cx, y=cy), end=Point(x=end[0], y=end[1], z=ez),
              direction=direction, segments=_ARC_SEGMENTS)
    geom = arc_geometry(arc, cur.x, cur.y, cur.z)
    pts = tuple(arc_points(arc, cur.x, cur.y, cur.z, geom))

    speed = _emit_speed_control(words, cur, on, events)

    deposited_volume = delta_e / cur.volume_to_e if cur.volume_to_e else 0.0
    filament_length = delta_e
    events.append(Segment(
        start=start, end=(end[0], end[1], ez if ez is not None else cur.z),
        travel=not on, speed=speed, length=geom.arc_length,
        deposited_volume=deposited_volume, filament_length=filament_length,
        source_index=lineno, kind='arc', centre=(cx, cy), clockwise=clockwise,
        width=cur.width, height=cur.height, arc_points=pts))
    cur.x = end[0]
    cur.y = end[1]
    cur.z = ez if ez is not None else cur.z


def _handle_g92(raw, code, cur, events):
    'G92 sets the logical position. G92 E0 (or any E) resets the E accumulator (no segment).'
    words = _tokenise(code)
    if 'E' in words:
        cur.e_total = words['E']
    if 'X' in words:
        cur.x = words['X']
    if 'Y' in words:
        cur.y = words['Y']
    if 'Z' in words:
        cur.z = words['Z']
    events.append(ManualGcode(text=raw))
