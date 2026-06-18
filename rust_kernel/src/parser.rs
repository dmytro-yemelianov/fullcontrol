//! G-code -> Toolpath IR parser (the inverse of g-code emission).
//!
//! A line-by-line port of `fullcontrol/gcode_engine/parser.py`. It holds the same running parse
//! context (position cursor, extruder on/off, running speed, E accumulator, volume<->E ratio) and
//! emits the SAME IR JSON the Python parser produces, so `fullcontrol.ir.serialize.from_json`
//! rebuilds an identical `Toolpath`.
//!
//! Motion (G0/G1/G2/G3 incl. arcs via centre/clockwise + arc length), M-code -> pass-through
//! `ManualGcode` steps, comment/unknown -> verbatim `ManualGcode`, E -> filament_length/volume
//! reconstruction, G92 E0 reset, and the never-panic behaviour all mirror the reference. The arc
//! geometry/tessellation reproduces `fullcontrol/core/arc.py` (`arc_geometry` + `arc_points`).

use serde_json::{json, Map, Value};
use std::f64::consts::{PI, TAU};

/// Number of straight segments used to render an arc (matches `_ARC_SEGMENTS` / `Arc.segments`).
const ARC_SEGMENTS: usize = 100;

// The arc tessellation must reproduce CPython's `math` (the Python parser uses) bit-for-bit, so the
// arc_points round-trip identically. CPython's `math.sin`/`cos`/`atan2`/`hypot` call the platform's
// C library; Rust's `f64` methods may select a different (LTO-folded / vectorised) implementation
// under the release build, which can differ by 1 ULP. Binding the same libc symbols the interpreter
// uses guarantees identical rounding. These are thin, side-effect-free wrappers.
extern "C" {
    fn sin(x: f64) -> f64;
    fn cos(x: f64) -> f64;
    fn atan2(y: f64, x: f64) -> f64;
    fn hypot(x: f64, y: f64) -> f64;
}

fn libm_sin(x: f64) -> f64 {
    // SAFETY: `sin` is a pure libc math function with no preconditions on its f64 argument.
    unsafe { sin(x) }
}

fn libm_cos(x: f64) -> f64 {
    // SAFETY: `cos` is a pure libc math function with no preconditions on its f64 argument.
    unsafe { cos(x) }
}

fn libm_atan2(y: f64, x: f64) -> f64 {
    // SAFETY: `atan2` is a pure libc math function with no preconditions on its f64 arguments.
    unsafe { atan2(y, x) }
}

fn libm_hypot(x: f64, y: f64) -> f64 {
    // SAFETY: `hypot` is a pure libc math function with no preconditions on its f64 arguments.
    unsafe { hypot(x, y) }
}

/// The dialect emits motion words in this fixed order: [F] X Y Z [I J] E.
const CANONICAL_ORDER: [char; 7] = ['F', 'X', 'Y', 'Z', 'I', 'J', 'E'];

/// Parsing context the parser needs (mirror of Python `ParseParams`). `relative_e` is part of the
/// `ParseParams` JSON the Python dataclass produces but, like the Python `_Cursor`, the parser does
/// not read it (the E mode is driven by the M82/M83 lines actually present in the stream, not by the
/// params flag), so it is not stored here. `from_json` simply ignores that key.
pub struct ParseParams {
    pub flavor: String,
    pub e_units: String,
    pub dia_feed: f64,
    pub travel_g1_e0: bool,
}

impl ParseParams {
    /// Build from a JSON object: {flavor, relative_e, e_units, dia_feed, travel_g1_e0}. Missing
    /// keys fall back to the Python dataclass defaults; `relative_e` is accepted but unused.
    pub fn from_json(v: &Value) -> ParseParams {
        ParseParams {
            flavor: v["flavor"].as_str().unwrap_or("marlin").to_string(),
            e_units: v["e_units"].as_str().unwrap_or("mm").to_string(),
            dia_feed: v["dia_feed"].as_f64().unwrap_or(1.75),
            travel_g1_e0: v["travel_g1_e0"].as_bool().unwrap_or(false),
        }
    }
}

/// Mirror `_volume_to_e`: mm3 -> 1, mm -> 1/(pi r^2).
fn volume_to_e(params: &ParseParams) -> f64 {
    if params.e_units == "mm3" {
        1.0
    } else {
        1.0 / (PI * (params.dia_feed / 2.0).powi(2))
    }
}

/// The extrusion-mode lines a flavor's dialect emits (mirror of `flavor.extrusion_mode`). The
/// supported flavors ('marlin' | 'klipper' | 'duet' | 'reprapfirmware') all emit identical M82/M83
/// mode lines - the flavor only changes other vocabulary - so `flavor` is accepted and validated
/// here for fidelity with `get_flavor(params.flavor)` without altering the output.
fn extrusion_mode(_flavor: &str, relative: bool) -> String {
    if relative {
        "M83 ; relative extrusion".to_string()
    } else {
        "M82 ; absolute extrusion\nG92 E0 ; reset extrusion position to zero".to_string()
    }
}

/// The running parse context (mirror of Python `_Cursor`).
struct Cursor {
    travel_g1_e0: bool,
    mode_rel: String,
    mode_abs: String,
    volume_to_e: f64,
    x: Option<f64>,
    y: Option<f64>,
    z: Option<f64>,
    relative_xyz: bool,
    relative_e: bool,
    e_total: f64,
    on: bool,
    cur_speed: Option<f64>,
    width: Option<f64>,
    height: Option<f64>,
}

impl Cursor {
    fn new(params: &ParseParams) -> Cursor {
        Cursor {
            travel_g1_e0: params.travel_g1_e0,
            mode_rel: extrusion_mode(&params.flavor, true),
            mode_abs: extrusion_mode(&params.flavor, false),
            volume_to_e: volume_to_e(params),
            x: None,
            y: None,
            z: None,
            relative_xyz: false,
            relative_e: false,
            e_total: 0.0,
            on: false,
            cur_speed: None,
            width: None,
            height: None,
        }
    }
}

/// Split a command word-list into {letter: float}. A token whose value does not parse is skipped
/// (the caller inherits the previous value). Mirror of `_tokenise`.
fn tokenise(code: &str) -> Map<String, Value> {
    let mut words = Map::new();
    for tok in code.split_whitespace() {
        let mut chars = tok.chars();
        let letter = match chars.next() {
            Some(c) => c.to_ascii_uppercase(),
            None => continue,
        };
        if "GXYZEFIJRS".contains(letter) {
            let rest = &tok[1..];
            if let Some(val) = parse_float(rest) {
                words.insert(letter.to_string(), json!(val));
            }
        }
    }
    words
}

/// Parse a float exactly as Python's `float()` accepts it for these tokens. Python's `float`
/// rejects e.g. an empty string or a bare sign; Rust's `f64::from_str` matches closely enough for
/// the numeric forms g-code uses (it also accepts leading/trailing whitespace, which never occurs
/// inside a token here). A value Python would reject (e.g. "") returns None -> token skipped.
fn parse_float(s: &str) -> Option<f64> {
    s.trim().parse::<f64>().ok()
}

/// Return (code, had_comment). Everything after the first ';' is a comment. Mirror `_strip_comment`.
fn strip_comment(line: &str) -> (String, bool) {
    match line.find(';') {
        None => (line.trim().to_string(), false),
        Some(idx) => (line[..idx].trim().to_string(), true),
    }
}

/// Parse g-code text into the serialized Toolpath IR (the JSON `fullcontrol.ir.serialize.from_json`
/// consumes). Never panics on malformed input.
pub fn parse_gcode(text: &str, params: &ParseParams) -> Value {
    let mut cur = Cursor::new(params);
    let mut events: Vec<Value> = Vec::new();
    if text.is_empty() {
        return json!({"version": 1, "events": events});
    }

    // split (not lines()) preserves exact line structure, matching Python's `text.split('\n')`.
    let lines: Vec<&str> = text.split('\n').collect();
    let mut i = 0;
    while i < lines.len() {
        let raw = lines[i];
        let lineno = (i + 1) as i64;
        let consumed = parse_line(raw, lineno, &mut cur, &mut events, &lines, i);
        i += consumed;
    }

    json!({"version": 1, "events": events})
}

/// Dispatch one line. Returns the number of source lines consumed (usually 1; the absolute-mode
/// "M82\nG92 E0" block consumes 2). Mirror of `_parse_line`.
fn parse_line(
    raw: &str,
    lineno: i64,
    cur: &mut Cursor,
    events: &mut Vec<Value>,
    lines: &[&str],
    idx: usize,
) -> usize {
    let (code, had_comment) = strip_comment(raw);

    if code.is_empty() {
        scan_comment_hints(raw, cur);
        events.push(manual_gcode(raw));
        return 1;
    }

    let head = code.split_whitespace().next().unwrap().to_ascii_uppercase();

    let is_motion = matches!(
        head.as_str(),
        "G0" | "G00" | "G1" | "G01" | "G2" | "G02" | "G3" | "G03"
    );
    if is_motion {
        let toks: Vec<&str> = code.split_whitespace().collect();
        let has_f = toks[1..]
            .iter()
            .any(|t| t.chars().next().map(|c| c.to_ascii_uppercase()) == Some('F'));
        let no_speed_yet = !has_f && cur.cur_speed.is_none();
        let not_tight = raw != raw.trim() || code.contains("  ");
        if had_comment || not_tight || !is_canonical_motion(&head, &code) || no_speed_yet {
            events.push(manual_gcode(raw));
            return 1;
        }
    }

    match head.as_str() {
        "G0" | "G00" | "G1" | "G01" => handle_linear(&code, lineno, cur, events),
        "G2" | "G02" | "G3" | "G03" => {
            let clockwise = matches!(head.as_str(), "G2" | "G02");
            handle_arc(raw, &code, lineno, cur, events, clockwise)
        }
        "G92" => handle_g92(raw, &code, cur, events),
        "G90" => {
            cur.relative_xyz = false;
            events.push(manual_gcode(raw));
        }
        "M82" | "M83" => return handle_extrusion_mode(raw, &head, cur, events, lines, idx),
        _ => events.push(manual_gcode(raw)),
    }
    1
}

/// M82/M83 set the E mode. Mirror of `_handle_extrusion_mode`.
fn handle_extrusion_mode(
    raw: &str,
    head: &str,
    cur: &mut Cursor,
    events: &mut Vec<Value>,
    lines: &[&str],
    idx: usize,
) -> usize {
    if head == "M83" {
        cur.relative_e = true;
        if raw == cur.mode_rel {
            events.push(extruder_step(Some(true)));
            cur.e_total = 0.0;
            return 1;
        }
        events.push(manual_gcode(raw));
        return 1;
    }
    // head == "M82"
    cur.relative_e = false;
    let block: Vec<&str> = cur.mode_abs.split('\n').collect();
    if block.len() == 2 && raw == block[0] && idx + 1 < lines.len() && lines[idx + 1] == block[1] {
        events.push(extruder_step(Some(false)));
        cur.e_total = 0.0;
        return 2;
    }
    events.push(manual_gcode(raw));
    1
}

/// True iff the line is a FullControl-emitted motion line reconstructable byte-identically. Mirror
/// of `_is_canonical_motion`.
fn is_canonical_motion(head: &str, code: &str) -> bool {
    let mut rank: i64 = -1;
    let mut letters: Vec<char> = Vec::new();
    for tok in code.split_whitespace().skip(1) {
        let letter = match tok.chars().next() {
            Some(c) => c.to_ascii_uppercase(),
            None => return false,
        };
        let r = match CANONICAL_ORDER.iter().position(|&c| c == letter) {
            Some(p) => p as i64,
            None => return false,
        };
        if r <= rank {
            return false;
        }
        rank = r;
        letters.push(letter);
        if parse_float(&tok[1..]).is_none() {
            return false;
        }
    }
    let has_axis = letters.iter().any(|c| matches!(c, 'X' | 'Y' | 'Z'));
    if !has_axis {
        return false;
    }
    if matches!(head, "G2" | "G02" | "G3" | "G03") {
        return letters.contains(&'I') && letters.contains(&'J');
    }
    if letters.contains(&'I') || letters.contains(&'J') {
        return false;
    }
    if matches!(head, "G1" | "G01") {
        return letters.contains(&'E');
    }
    !letters.contains(&'E')
}

/// Extract ;WIDTH:/;HEIGHT: hints for following segments. Mirror of `_scan_comment_hints`.
fn scan_comment_hints(raw: &str, cur: &mut Cursor) {
    let low = raw.to_lowercase();
    if low.contains(";width:") {
        if let Some(n) = num_after(&low, ";width:") {
            cur.width = Some(n);
        }
    }
    if low.contains(";height:") || low.contains(";layer_height:") {
        let key = if low.contains(";height:") {
            ";height:"
        } else {
            ";layer_height:"
        };
        if let Some(n) = num_after(&low, key) {
            cur.height = Some(n);
        }
    }
}

/// Pull the first (signed) number after `key`. Mirror of `_num_after` (`-?\d+\.?\d*`).
fn num_after(s: &str, key: &str) -> Option<f64> {
    let seg = s.split_once(key).map(|(_, rest)| rest)?;
    let bytes = seg.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let c = bytes[i];
        let start_ok = c == b'-' && i + 1 < bytes.len() && bytes[i + 1].is_ascii_digit();
        if c.is_ascii_digit() || start_ok {
            let begin = i;
            if c == b'-' {
                i += 1;
            }
            while i < bytes.len() && bytes[i].is_ascii_digit() {
                i += 1;
            }
            if i < bytes.len() && bytes[i] == b'.' {
                i += 1;
                while i < bytes.len() && bytes[i].is_ascii_digit() {
                    i += 1;
                }
            }
            return seg[begin..i].parse::<f64>().ok();
        }
        i += 1;
    }
    None
}

/// Apply X/Y/Z words to the cursor (absolute or relative), returning (start, end). Mirror of
/// `_resolve_xyz`. Each axis is an Option<f64> (None = undefined).
fn resolve_xyz(words: &Map<String, Value>, cur: &Cursor) -> ([Option<f64>; 3], [Option<f64>; 3]) {
    let (sx, sy, sz) = (cur.x, cur.y, cur.z);
    let resolve = |axis: &str, s: Option<f64>| -> Option<f64> {
        match words.get(axis).and_then(|v| v.as_f64()) {
            None => s,
            Some(w) => {
                if cur.relative_xyz {
                    Some(s.unwrap_or(0.0) + w)
                } else {
                    Some(w)
                }
            }
        }
    };
    let end = [resolve("X", sx), resolve("Y", sy), resolve("Z", sz)];
    ([sx, sy, sz], end)
}

/// The E delta (gcode units), updating the accumulator. 0 if no E word. Mirror of `_delta_e`.
fn delta_e(words: &Map<String, Value>, cur: &mut Cursor) -> f64 {
    let e = match words.get("E").and_then(|v| v.as_f64()) {
        None => return 0.0,
        Some(e) => e,
    };
    if cur.relative_e {
        cur.e_total += e;
        e
    } else {
        let delta = e - cur.e_total;
        cur.e_total = e;
        delta
    }
}

/// Euclidean length, ignoring an axis undefined in either endpoint. Mirror of `_length`.
fn length(start: &[Option<f64>; 3], end: &[Option<f64>; 3]) -> f64 {
    let comp = |a: Option<f64>, b: Option<f64>| -> f64 {
        match (a, b) {
            (Some(a), Some(b)) => b - a,
            _ => 0.0,
        }
    };
    let dx = comp(start[0], end[0]);
    let dy = comp(start[1], end[1]);
    let dz = comp(start[2], end[2]);
    (dx * dx + dy * dy + dz * dz).sqrt()
}

/// Reproduce the dialect's F-word: insert a Printer speed event iff the line carried an F word.
/// Mirror of `_emit_speed_control`. Returns the effective speed for the segment.
fn emit_speed_control(
    words: &Map<String, Value>,
    cur: &mut Cursor,
    on: bool,
    events: &mut Vec<Value>,
) -> f64 {
    cur.on = on;
    match words.get("F").and_then(|v| v.as_f64()) {
        None => cur.cur_speed.unwrap_or(0.0),
        Some(speed) => {
            cur.cur_speed = Some(speed);
            events.push(printer_step(speed, speed));
            speed
        }
    }
}

/// Handle G0/G1 linear move. Mirror of `_handle_linear`.
fn handle_linear(code: &str, lineno: i64, cur: &mut Cursor, events: &mut Vec<Value>) {
    let words = tokenise(code);
    let head = code.split_whitespace().next().unwrap().to_ascii_uppercase();
    let de = delta_e(&words, cur);
    let on = if matches!(head.as_str(), "G0" | "G00") {
        false
    } else if cur.travel_g1_e0 && de == 0.0 {
        cur.on
    } else {
        true
    };
    let (start, end) = resolve_xyz(&words, cur);
    let speed = emit_speed_control(&words, cur, on, events);
    let len = length(&start, &end);
    let deposited_volume = if cur.volume_to_e != 0.0 {
        de / cur.volume_to_e
    } else {
        0.0
    };
    events.push(segment_line(Seg {
        start,
        end,
        travel: !on,
        speed,
        length: len,
        deposited_volume,
        filament_length: de,
        source_index: lineno,
        width: cur.width,
        height: cur.height,
    }));
    cur.x = end[0];
    cur.y = end[1];
    cur.z = end[2];
}

/// Handle G2/G3 arc move. Mirror of `_handle_arc`.
fn handle_arc(
    raw: &str,
    code: &str,
    lineno: i64,
    cur: &mut Cursor,
    events: &mut Vec<Value>,
    clockwise: bool,
) {
    let words = tokenise(code);
    let (sx, sy, sz) = (cur.x, cur.y, cur.z);
    if sx.is_none() || sy.is_none() || !words.contains_key("I") || !words.contains_key("J") {
        events.push(manual_gcode(raw));
        return;
    }
    let de = delta_e(&words, cur);
    let on = de > 0.0;
    let (start, end) = resolve_xyz(&words, cur);
    let (sx, sy) = (sx.unwrap(), sy.unwrap());
    let cx = sx + words["I"].as_f64().unwrap();
    let cy = sy + words["J"].as_f64().unwrap();
    let ez = end[2];

    let geom = arc_geometry(&ArcInput {
        cx,
        cy,
        ex: end[0],
        ey: end[1],
        ez,
        sx,
        sy,
        sz,
        clockwise,
    });
    let pts = arc_points(&geom, end[0], end[1], ez, sz);

    let speed = emit_speed_control(&words, cur, on, events);
    let deposited_volume = if cur.volume_to_e != 0.0 {
        de / cur.volume_to_e
    } else {
        0.0
    };
    let seg_end_z = if ez.is_some() { ez } else { cur.z };
    events.push(segment_arc(
        Seg {
            start,
            end: [end[0], end[1], seg_end_z],
            travel: !on,
            speed,
            length: geom.arc_length,
            deposited_volume,
            filament_length: de,
            source_index: lineno,
            width: cur.width,
            height: cur.height,
        },
        cx,
        cy,
        clockwise,
        &pts,
    ));
    cur.x = end[0];
    cur.y = end[1];
    cur.z = if ez.is_some() { ez } else { cur.z };
}

/// Resolved arc geometry (mirror of `fullcontrol.core.arc.ArcGeometry`).
struct ArcGeometry {
    clockwise: bool,
    cx: f64,
    cy: f64,
    radius: f64,
    start_angle: f64,
    swept: f64,
    dz: f64,
    arc_length: f64,
}

/// Mirror of `arc_geometry`. `(cx, cy)` is the centre, `(sx, sy, sz)` the start, `end` the resolved
/// end coordinates and `clockwise` the direction. The radius tolerance check is omitted: the parser
/// only reaches here once it has a valid start + I/J, and any geometric inconsistency does not raise
/// in the Python parser either (its outer try/except yields a ManualGcode; reproduced by the
/// never-panic walk).
/// Resolved-coordinate inputs to `arc_geometry` (grouped to keep the signature small).
struct ArcInput {
    cx: f64,
    cy: f64,
    ex: Option<f64>,
    ey: Option<f64>,
    ez: Option<f64>,
    sx: f64,
    sy: f64,
    sz: Option<f64>,
    clockwise: bool,
}

/// Python's float `%` (a floored remainder): the result has the sign of the divisor (TAU > 0, so
/// the result is in [0, TAU)). Mirrors `(angle) % tau` from `arc_geometry` exactly.
fn py_mod_tau(x: f64) -> f64 {
    let r = x % TAU;
    if r != 0.0 && (r < 0.0) != (TAU < 0.0) {
        r + TAU
    } else {
        r
    }
}

fn arc_geometry(a: &ArcInput) -> ArcGeometry {
    let ex = a.ex.unwrap_or(a.sx);
    let ey = a.ey.unwrap_or(a.sy);
    let radius = libm_hypot(a.sx - a.cx, a.sy - a.cy);
    let start_angle = libm_atan2(a.sy - a.cy, a.sx - a.cx);
    let end_angle = libm_atan2(ey - a.cy, ex - a.cx);
    let mut swept = if a.clockwise {
        py_mod_tau(start_angle - end_angle)
    } else {
        py_mod_tau(end_angle - start_angle)
    };
    if swept == 0.0 {
        swept = TAU;
    }
    let dz = match (a.ez, a.sz) {
        (Some(ez), Some(sz)) => ez - sz,
        _ => 0.0,
    };
    let arc_length = libm_hypot(radius * swept, dz);
    ArcGeometry {
        clockwise: a.clockwise,
        cx: a.cx,
        cy: a.cy,
        radius,
        start_angle,
        swept,
        dz,
        arc_length,
    }
}

/// Mirror of `arc_points`: tessellate into ARC_SEGMENTS (x, y, z) points after the start.
fn arc_points(
    geom: &ArcGeometry,
    ex: Option<f64>,
    ey: Option<f64>,
    ez: Option<f64>,
    sz: Option<f64>,
) -> Vec<[Option<f64>; 3]> {
    let sign = if geom.clockwise { -1.0 } else { 1.0 };
    let mut points = Vec::with_capacity(ARC_SEGMENTS);
    for i in 1..=ARC_SEGMENTS {
        let (px, py, pz) = if i == ARC_SEGMENTS {
            let pz = if ez.is_some() { ez } else { sz };
            (ex, ey, pz)
        } else {
            let frac = i as f64 / ARC_SEGMENTS as f64;
            let angle = geom.start_angle + sign * geom.swept * frac;
            let px = geom.cx + geom.radius * libm_cos(angle);
            let py = geom.cy + geom.radius * libm_sin(angle);
            let pz = match sz {
                Some(sz) => Some(sz + geom.dz * frac),
                None => ez,
            };
            (Some(px), Some(py), pz)
        };
        points.push([px, py, pz]);
    }
    points
}

/// G92 sets the logical position; G92 E resets the E accumulator. Mirror of `_handle_g92`.
fn handle_g92(raw: &str, code: &str, cur: &mut Cursor, events: &mut Vec<Value>) {
    let words = tokenise(code);
    if let Some(e) = words.get("E").and_then(|v| v.as_f64()) {
        cur.e_total = e;
    }
    if let Some(x) = words.get("X").and_then(|v| v.as_f64()) {
        cur.x = Some(x);
    }
    if let Some(y) = words.get("Y").and_then(|v| v.as_f64()) {
        cur.y = Some(y);
    }
    if let Some(z) = words.get("Z").and_then(|v| v.as_f64()) {
        cur.z = Some(z);
    }
    events.push(manual_gcode(raw));
}

// --- IR JSON builders (the exact shapes `fullcontrol.ir.serialize` produces) ---

fn opt(v: Option<f64>) -> Value {
    match v {
        Some(f) => json!(f),
        None => Value::Null,
    }
}

fn xyz_array(v: &[Option<f64>; 3]) -> Value {
    Value::Array(vec![opt(v[0]), opt(v[1]), opt(v[2])])
}

fn manual_gcode(text: &str) -> Value {
    json!({"k": "step", "type": "ManualGcode", "data": {"text": text}})
}

fn extruder_step(relative_gcode: Option<bool>) -> Value {
    json!({
        "k": "step",
        "type": "Extruder",
        "data": {
            "on": Value::Null,
            "units": Value::Null,
            "dia_feed": Value::Null,
            "relative_gcode": relative_gcode,
        }
    })
}

fn printer_step(print_speed: f64, travel_speed: f64) -> Value {
    json!({
        "k": "step",
        "type": "Printer",
        "data": {
            "print_speed": print_speed,
            "travel_speed": travel_speed,
            "new_command": Value::Null,
        }
    })
}

/// The shared fields of a resolved `Segment` (grouped to keep builder signatures small).
struct Seg {
    start: [Option<f64>; 3],
    end: [Option<f64>; 3],
    travel: bool,
    speed: f64,
    length: f64,
    deposited_volume: f64,
    filament_length: f64,
    source_index: i64,
    width: Option<f64>,
    height: Option<f64>,
}

fn segment_line(s: Seg) -> Value {
    json!({
        "k": "segment",
        "start": xyz_array(&s.start),
        "end": xyz_array(&s.end),
        "travel": s.travel,
        "speed": s.speed,
        "length": s.length,
        "deposited_volume": s.deposited_volume,
        "filament_length": s.filament_length,
        "source_index": s.source_index,
        "kind": "line",
        "centre": Value::Null,
        "clockwise": false,
        "width": opt(s.width),
        "height": opt(s.height),
        "color": Value::Null,
        "arc_points": Value::Null,
    })
}

fn segment_arc(
    s: Seg,
    cx: f64,
    cy: f64,
    clockwise: bool,
    arc_points: &[[Option<f64>; 3]],
) -> Value {
    let pts: Vec<Value> = arc_points.iter().map(xyz_array).collect();
    json!({
        "k": "segment",
        "start": xyz_array(&s.start),
        "end": xyz_array(&s.end),
        "travel": s.travel,
        "speed": s.speed,
        "length": s.length,
        "deposited_volume": s.deposited_volume,
        "filament_length": s.filament_length,
        "source_index": s.source_index,
        "kind": "arc",
        "centre": [cx, cy],
        "clockwise": clockwise,
        "width": opt(s.width),
        "height": opt(s.height),
        "color": Value::Null,
        "arc_points": Value::Array(pts),
    })
}
