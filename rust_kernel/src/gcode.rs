//! G-code emission from the serialized Toolpath IR (fullcontrol/ir/serialize.py format).
//!
//! Consumes the IR JSON and emits g-code byte-for-byte identical to the Python dialect + Marlin
//! flavor (`fullcontrol/gcode/dialect.py`, `flavor.py`, `renderers.py`).
//!
//! `emit_moves` emits the motion lines only (G0/G1/G2/G3 + stationary extrusion) - for callers that
//! already have the procedures/commands (or don't want them). `emit_gcode` additionally emits the
//! common non-motion commands - extrusion mode (M82/M83), hotend/bed temperature, fan, and
//! pass-through ManualGcode - so a design resolved *with* procedures round-trips to a full file.
//!
//! Marlin flavor only; NOT yet emitted (the next surface, kept in Python): retraction, acceleration
//! /jerk/pressure-advance, PrinterCommand command-lists, GcodeComment line-append, other firmwares.

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

/// Format a JSON number as Python's `f'{n}'` would (an int stays an int, e.g. a temperature/speed).
fn num_word(v: &Value) -> String {
    if let Some(i) = v.as_i64() {
        i.to_string()
    } else {
        format!("{}", v.as_f64().unwrap_or(0.0))
    }
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

// --- Marlin flavor vocabulary (mirrors fullcontrol/gcode/flavor.py) ---

fn extrusion_mode(relative: bool) -> String {
    if relative {
        "M83 ; relative extrusion".to_string()
    } else {
        "M82 ; absolute extrusion\nG92 E0 ; reset extrusion position to zero".to_string()
    }
}

fn hotend_temp(temp: &Value, wait: bool, tool: &Value) -> String {
    let t = num_word(temp);
    match (tool.is_null(), wait) {
        (true, false) => format!("M104 S{t} ; set hotend temp and continue"),
        (true, true) => format!("M109 S{t} ; set hotend temp and wait"),
        (false, false) => {
            let tl = num_word(tool);
            format!("M104 S{t} T{tl} ; set hotend temp for tool {tl} and continue")
        }
        (false, true) => {
            let tl = num_word(tool);
            format!("M109 S{t} T{tl} ; set hotend temp for tool {tl} and wait")
        }
    }
}

fn bed_temp(temp: &Value, wait: bool) -> String {
    let t = num_word(temp);
    if wait {
        format!("M190 S{t} ; set bed temp and wait")
    } else {
        format!("M140 S{t} ; set bed temp and continue")
    }
}

fn fan(speed_percent: f64) -> String {
    let pwm = (speed_percent * 255.0 / 100.0) as i64; // Python int(): truncates toward zero
    format!("M106 S{pwm} ; set fan speed")
}

/// Core fold over the IR. `full` enables non-motion command emission; otherwise only motion lines
/// (and the speed_changed bookkeeping) are produced.
fn emit(ir: &Value, relative_e: bool, travel_g1_e0: bool, full: bool) -> Vec<String> {
    let mut out = Vec::new();
    let mut speed_changed = true;
    let mut e_total = 0.0_f64;
    let mut relative = relative_e;
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
                let e_str = e_word(fil, travel, relative, travel_g1_e0, &mut e_total);
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
                let e = if relative {
                    fil
                } else {
                    e_total += fil;
                    e_total
                };
                out.push(format!("G1 F{} E{}", num_word(&ev["speed"]), fmt(e, 6)));
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
                    Some("Extruder") => {
                        if !data["on"].is_null() {
                            speed_changed = true;
                        }
                        if full && !data["relative_gcode"].is_null() {
                            relative = data["relative_gcode"].as_bool().unwrap_or(false);
                            out.push(extrusion_mode(relative));
                        }
                    }
                    Some("Retraction") | Some("Unretraction") => speed_changed = true,
                    Some("Hotend") if full && !data["temp"].is_null() => out.push(hotend_temp(
                        &data["temp"],
                        data["wait"].as_bool().unwrap_or(false),
                        &data["tool"],
                    )),
                    Some("Buildplate") if full && !data["temp"].is_null() => out.push(bed_temp(
                        &data["temp"],
                        data["wait"].as_bool().unwrap_or(false),
                    )),
                    Some("Fan") if full && !data["speed_percent"].is_null() => {
                        out.push(fan(data["speed_percent"].as_f64().unwrap_or(0.0)))
                    }
                    Some("ManualGcode") if full && !data["text"].is_null() => {
                        out.push(data["text"].as_str().unwrap_or("").to_string())
                    }
                    _ => {}
                }
            }
            _ => {}
        }
    }
    out
}

/// Emit only the motion lines (G0/G1/G2/G3 + stationary extrusion) for an IR document.
pub fn emit_moves(ir: &Value, relative_e: bool, travel_g1_e0: bool) -> Vec<String> {
    emit(ir, relative_e, travel_g1_e0, false)
}

/// Emit a full g-code line list (motion + the common non-motion commands) for an IR document
/// resolved with procedures. Join with '\n' to get the file.
pub fn emit_gcode(ir: &Value, relative_e: bool, travel_g1_e0: bool) -> Vec<String> {
    emit(ir, relative_e, travel_g1_e0, true)
}
