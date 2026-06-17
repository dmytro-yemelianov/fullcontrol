//! G-code motion emission from the serialized Toolpath IR (fullcontrol/ir/serialize.py format).
//!
//! Consumes the IR JSON and emits the motion lines - G0/G1 linear moves, G2/G3 arcs, and the
//! stationary-extrusion (MaterialEvent) lines - byte-for-byte identical to the Python gcode
//! dialect (`fullcontrol/gcode/dialect.py`). This is the per-move hot path of g-code generation
//! (one formatted line per move); the surrounding orchestration that this increment does NOT yet
//! emit - the start/end procedures, retraction/temperature/fan commands, the M82/M83 mode line,
//! and non-Marlin flavours - stays in Python and is the enumerated next surface.
//!
//! `speed_changed` (whether a move prefixes an F word) follows the dialect exactly: it starts true,
//! a move consumes it, and it is re-armed by a MaterialEvent or by a pass-through Printer (with a
//! speed), Extruder (with `on`), Retraction or Unretraction step.

use serde_json::Value;

/// gcode number format: fixed `dp` decimals, trailing zeros (and the dot) stripped. Matches the
/// Python `number_format.fmt` byte-for-byte (verified across rounding edge cases).
fn fmt(v: f64, dp: usize) -> String {
    let s = format!("{:.*}", dp, v);
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

/// A coordinate from the IR: a JSON number, or null for an undefined axis.
fn axis(v: &Value) -> Option<f64> {
    if v.is_null() {
        None
    } else {
        v.as_f64()
    }
}

fn xyz(v: &Value) -> [Option<f64>; 3] {
    [axis(&v[0]), axis(&v[1]), axis(&v[2])]
}

/// X/Y/Z words for axes that are defined and changed (mirrors dialect `_axes`).
fn axes_str(start: &[Option<f64>; 3], end: &[Option<f64>; 3]) -> String {
    let mut s = String::new();
    for (label, a, b) in [
        ('X', start[0], end[0]),
        ('Y', start[1], end[1]),
        ('Z', start[2], end[2]),
    ] {
        if let Some(bv) = b {
            if a != Some(bv) {
                s.push_str(&format!("{}{} ", label, fmt(bv, 6)));
            }
        }
    }
    s
}

/// The E word for a move (mirrors dialect `_e_word`). `e_total` is the absolute-mode accumulator.
fn e_word(
    filament_length: f64,
    travel: bool,
    relative: bool,
    travel_g1_e0: bool,
    e_total: &mut f64,
) -> String {
    if !travel {
        if relative {
            format!("E{}", fmt(filament_length, 6))
        } else {
            *e_total += filament_length;
            format!("E{}", fmt(*e_total, 6))
        }
    } else if travel_g1_e0 {
        if relative {
            "E0".to_string()
        } else {
            format!("E{}", fmt(*e_total, 6))
        }
    } else {
        String::new()
    }
}

/// Format a MaterialEvent / stationary speed as Python's `f'{speed}'` would (an int stays an int).
fn speed_word(v: &Value) -> String {
    if let Some(i) = v.as_i64() {
        i.to_string()
    } else {
        fmt(v.as_f64().unwrap_or(0.0), 1)
    }
}

/// Emit the motion lines for an IR document (the parsed `to_json` output).
pub fn emit_moves(ir: &Value, relative_e: bool, travel_g1_e0: bool) -> Vec<String> {
    let mut out = Vec::new();
    let mut speed_changed = true;
    let mut e_total = 0.0_f64;
    let empty: Vec<Value> = Vec::new();
    let events = ir
        .get("events")
        .and_then(|e| e.as_array())
        .unwrap_or(&empty);

    for ev in events {
        match ev.get("k").and_then(|k| k.as_str()) {
            Some("segment") => {
                let start = xyz(&ev["start"]);
                let end = xyz(&ev["end"]);
                let travel = ev["travel"].as_bool().unwrap_or(false);
                let speed = ev["speed"].as_f64().unwrap_or(0.0);
                let fil = ev["filament_length"].as_f64().unwrap_or(0.0);
                let f_str = if speed_changed {
                    format!("F{} ", fmt(speed, 1))
                } else {
                    String::new()
                };
                let e_str = e_word(fil, travel, relative_e, travel_g1_e0, &mut e_total);
                let line = if ev["kind"].as_str() == Some("arc") {
                    let mut coords = format!(
                        "X{} Y{} ",
                        fmt(end[0].unwrap_or(0.0), 6),
                        fmt(end[1].unwrap_or(0.0), 6)
                    );
                    if let Some(ez) = end[2] {
                        if start[2] != Some(ez) {
                            coords.push_str(&format!("Z{} ", fmt(ez, 6)));
                        }
                    }
                    let centre = &ev["centre"];
                    let (cx, cy) = (
                        centre[0].as_f64().unwrap_or(0.0),
                        centre[1].as_f64().unwrap_or(0.0),
                    );
                    let ij = format!(
                        "I{} J{} ",
                        fmt(cx - start[0].unwrap_or(0.0), 6),
                        fmt(cy - start[1].unwrap_or(0.0), 6)
                    );
                    let g = if ev["clockwise"].as_bool().unwrap_or(false) {
                        "G2 "
                    } else {
                        "G3 "
                    };
                    format!("{}{}{}{}{}", g, f_str, coords, ij, e_str)
                } else {
                    let g = if !travel || !e_str.is_empty() {
                        "G1 "
                    } else {
                        "G0 "
                    };
                    format!("{}{}{}{}", g, f_str, axes_str(&start, &end), e_str)
                };
                out.push(line.trim().to_string());
                speed_changed = false;
            }
            Some("material") => {
                let fil = ev["filament_length"].as_f64().unwrap_or(0.0);
                let e = if relative_e {
                    fil
                } else {
                    e_total += fil;
                    e_total
                };
                out.push(format!("G1 F{} E{}", speed_word(&ev["speed"]), fmt(e, 6)));
                speed_changed = true;
            }
            Some("step") => {
                let data = &ev["data"];
                match ev.get("type").and_then(|t| t.as_str()) {
                    Some("Printer")
                        if !data["print_speed"].is_null() || !data["travel_speed"].is_null() =>
                    {
                        speed_changed = true
                    }
                    Some("Extruder") if !data["on"].is_null() => speed_changed = true,
                    Some("Retraction") | Some("Unretraction") => speed_changed = true,
                    _ => {}
                }
            }
            _ => {}
        }
    }
    out
}
