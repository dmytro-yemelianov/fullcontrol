//! G-code emission from the serialized Toolpath IR (fullcontrol/ir/serialize.py format).
//!
//! Consumes the IR JSON and emits g-code byte-for-byte identical to the Python dialect + flavors
//! (`fullcontrol/gcode/dialect.py`, `flavor.py`, `renderers.py`).
//!
//! `emit_moves` emits the motion lines only (G0/G1/G2/G3 + stationary extrusion). `emit_gcode`
//! additionally emits every non-motion command of a design resolved *with* procedures: extrusion
//! mode, hotend/bed temperature, fan, ManualGcode, retraction/unretraction, acceleration, jerk,
//! pressure advance, PrinterCommand (via a command-list) and GcodeComment line-append - across the
//! marlin / klipper / duet(reprapfirmware) flavors.

use serde_json::{Map, Value};

/// Emission parameters (built on the Python side from the gcode `State`).
pub struct Params {
    pub relative_e: bool,
    pub travel_g1_e0: bool,
    pub flavor: String,
    pub retraction_distance: f64,
    pub retraction_speed: f64,
    pub command_list: Map<String, Value>,
}

impl Params {
    pub fn from_json(v: &Value) -> Params {
        Params {
            relative_e: v["relative_e"].as_bool().unwrap_or(false),
            travel_g1_e0: v["travel_g1_e0"].as_bool().unwrap_or(false),
            flavor: v["flavor"].as_str().unwrap_or("marlin").to_string(),
            retraction_distance: v["retraction_distance"].as_f64().unwrap_or(0.0),
            retraction_speed: v["retraction_speed"].as_f64().unwrap_or(0.0),
            command_list: v["command_list"].as_object().cloned().unwrap_or_default(),
        }
    }
    fn minimal(relative_e: bool, travel_g1_e0: bool) -> Params {
        Params {
            relative_e,
            travel_g1_e0,
            flavor: "marlin".to_string(),
            retraction_distance: 0.0,
            retraction_speed: 0.0,
            command_list: Map::new(),
        }
    }
}

/// gcode number format: fixed `dp` decimals, trailing zeros (and the dot) stripped. Matches the
/// Python `number_format.fmt` byte-for-byte (verified across rounding edge cases).
fn fmt(v: f64, dp: usize) -> String {
    let s = format!("{:.*}", dp, v);
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

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

/// The E value for a filament-length delta (relative: the delta; absolute: the running total).
fn e_for(delta: f64, relative: bool, e_total: &mut f64) -> f64 {
    if relative {
        delta
    } else {
        *e_total += delta;
        *e_total
    }
}

/// The E word for a move (mirrors dialect `_e_word`).
fn e_word(
    filament_length: f64,
    travel: bool,
    relative: bool,
    travel_g1_e0: bool,
    e_total: &mut f64,
) -> String {
    if !travel {
        format!("E{}", fmt(e_for(filament_length, relative, e_total), 6))
    } else if travel_g1_e0 {
        format!("E{}", fmt(e_for(0.0, relative, e_total), 6))
    } else {
        String::new()
    }
}

// --- flavor vocabulary (mirrors fullcontrol/gcode/flavor.py) ---

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

/// M204 P/R/T, omitting any axis left unset.
fn acceleration(data: &Value) -> Option<String> {
    let parts: Vec<String> = [("P", "printing"), ("R", "retract"), ("T", "travel")]
        .iter()
        .filter(|(_, k)| !data[*k].is_null())
        .map(|(tag, k)| format!("{}{}", tag, fmt(data[*k].as_f64().unwrap(), 6)))
        .collect();
    (!parts.is_empty()).then(|| format!("M204 {} ; set acceleration", parts.join(" ")))
}

fn jerk(data: &Value, flavor: &str) -> Option<String> {
    let (x, y, z, e) = (&data["x"], &data["y"], &data["z"], &data["e"]);
    match flavor {
        "klipper" => {
            let scv = if !x.is_null() { x } else { y };
            scv.as_f64()
                .map(|v| format!("SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY={}", fmt(v, 6)))
        }
        "duet" | "reprapfirmware" => {
            let parts = axis_parts(&[("X", x), ("Y", y), ("Z", z), ("E", e)], 60.0);
            (!parts.is_empty()).then(|| {
                format!(
                    "M566 {} ; set jerk (max instantaneous speed change)",
                    parts.join(" ")
                )
            })
        }
        _ => {
            let parts = axis_parts(&[("X", x), ("Y", y), ("Z", z), ("E", e)], 1.0);
            (!parts.is_empty()).then(|| format!("M205 {} ; set jerk", parts.join(" ")))
        }
    }
}

fn axis_parts(axes: &[(&str, &Value)], scale: f64) -> Vec<String> {
    axes.iter()
        .filter_map(|(tag, v)| v.as_f64().map(|f| format!("{}{}", tag, fmt(f * scale, 6))))
        .collect()
}

fn pressure_advance(data: &Value, flavor: &str) -> Option<String> {
    let value = data["value"].as_f64()?;
    let tool = &data["tool"];
    Some(match flavor {
        "klipper" => {
            let mut line = format!("SET_PRESSURE_ADVANCE ADVANCE={}", fmt(value, 6));
            if let Some(t) = tool.as_i64() {
                line += &format!(
                    " EXTRUDER=extruder{}",
                    if t == 0 { String::new() } else { t.to_string() }
                );
            }
            line
        }
        "duet" | "reprapfirmware" => {
            let drive = tool.as_i64().unwrap_or(0);
            format!("M572 D{drive} S{} ; set pressure advance", fmt(value, 6))
        }
        _ => {
            if tool.is_null() {
                format!("M900 K{} ; set pressure advance", fmt(value, 6))
            } else {
                format!(
                    "M900 T{} K{} ; set pressure advance",
                    num_word(tool),
                    fmt(value, 6)
                )
            }
        }
    })
}

/// Core fold over the IR. `full` enables non-motion command emission.
fn emit(ir: &Value, p: &Params, full: bool) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut speed_changed = true;
    let mut e_total = 0.0_f64;
    let mut relative = p.relative_e;
    let mut ret_dist = p.retraction_distance;
    let mut ret_speed = p.retraction_speed;
    let mut retracted = 0.0_f64;
    let mut commands = p.command_list.clone();
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
                let e_str = e_word(fil, travel, relative, p.travel_g1_e0, &mut e_total);
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
                let e = e_for(fil, relative, &mut e_total);
                out.push(format!("G1 F{} E{}", num_word(&ev["speed"]), fmt(e, 6)));
                speed_changed = true;
            }
            Some("step") if full => {
                emit_step(
                    ev,
                    p,
                    &mut out,
                    &mut speed_changed,
                    &mut e_total,
                    &mut relative,
                    &mut ret_dist,
                    &mut ret_speed,
                    &mut retracted,
                    &mut commands,
                );
            }
            Some("step") => {
                // motion-only: only the speed_changed bookkeeping for the toggling steps
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

#[allow(clippy::too_many_arguments)]
fn emit_step(
    ev: &Value,
    p: &Params,
    out: &mut Vec<String>,
    speed_changed: &mut bool,
    e_total: &mut f64,
    relative: &mut bool,
    ret_dist: &mut f64,
    ret_speed: &mut f64,
    retracted: &mut f64,
    commands: &mut Map<String, Value>,
) {
    let data = &ev["data"];
    match ev.get("type").and_then(|t| t.as_str()) {
        Some("Printer") => {
            if !data["print_speed"].is_null() || !data["travel_speed"].is_null() {
                *speed_changed = true;
            }
            if let Some(nc) = data["new_command"].as_object() {
                for (k, v) in nc {
                    commands.insert(k.clone(), v.clone());
                }
            }
        }
        Some("Extruder") => {
            if !data["on"].is_null() {
                *speed_changed = true;
            }
            if !data["relative_gcode"].is_null() {
                *relative = data["relative_gcode"].as_bool().unwrap_or(false);
                out.push(extrusion_mode(*relative));
            }
        }
        Some("Retraction") => {
            let dist = data["distance"].as_f64().unwrap_or(*ret_dist);
            let speed = data["speed"].as_f64().unwrap_or(*ret_speed);
            if dist != 0.0 {
                *ret_dist = dist;
                *ret_speed = speed;
                *retracted += dist;
                let e = e_for(-dist, *relative, e_total);
                out.push(format!("G1 F{} E{} ; retract", fmt(speed, 1), fmt(e, 6)));
                *speed_changed = true;
            }
        }
        Some("Unretraction") => {
            let dist = data["distance"].as_f64().unwrap_or(*retracted);
            let speed = data["speed"].as_f64().unwrap_or(*ret_speed);
            if dist != 0.0 {
                *retracted = (*retracted - dist).max(0.0);
                let e = e_for(dist, *relative, e_total);
                out.push(format!("G1 F{} E{} ; unretract", fmt(speed, 1), fmt(e, 6)));
                *speed_changed = true;
            }
        }
        Some("Hotend") if !data["temp"].is_null() => out.push(hotend_temp(
            &data["temp"],
            data["wait"].as_bool().unwrap_or(false),
            &data["tool"],
        )),
        Some("Buildplate") if !data["temp"].is_null() => out.push(bed_temp(
            &data["temp"],
            data["wait"].as_bool().unwrap_or(false),
        )),
        Some("Fan") if !data["speed_percent"].is_null() => {
            out.push(fan(data["speed_percent"].as_f64().unwrap_or(0.0)))
        }
        Some("ManualGcode") if !data["text"].is_null() => {
            out.push(data["text"].as_str().unwrap_or("").to_string())
        }
        Some("Acceleration") => {
            if let Some(line) = acceleration(data) {
                out.push(line);
            }
        }
        Some("Jerk") => {
            if let Some(line) = jerk(data, &p.flavor) {
                out.push(line);
            }
        }
        Some("PressureAdvance") => {
            if let Some(line) = pressure_advance(data, &p.flavor) {
                out.push(line);
            }
        }
        Some("PrinterCommand") => {
            if let Some(cmd) = data["id"]
                .as_str()
                .and_then(|id| commands.get(id))
                .and_then(|v| v.as_str())
            {
                out.push(cmd.to_string());
            }
        }
        Some("GcodeComment") => {
            if let Some(text) = data["end_of_previous_line_text"].as_str() {
                if let Some(last) = out.last_mut() {
                    last.push_str(&format!(" ; {text}"));
                }
            }
        }
        _ => {}
    }
}

/// Emit only the motion lines (G0/G1/G2/G3 + stationary extrusion) for an IR document.
pub fn emit_moves(ir: &Value, relative_e: bool, travel_g1_e0: bool) -> Vec<String> {
    emit(ir, &Params::minimal(relative_e, travel_g1_e0), false)
}

/// Emit a full g-code line list (motion + every non-motion command) for an IR document resolved
/// with procedures. Join with '\n' to get the file.
pub fn emit_gcode(ir: &Value, p: &Params) -> Vec<String> {
    emit(ir, p, true)
}
