//! wasm-bindgen binding for the microkernel - the same compute core, callable from JavaScript.
//!
//! The browser builds the flattened-step columns (tag + a/b/c/d) and the 10-element init context
//! exactly as `kernel.py` does on the Python side, then calls `simulate` to get the print metrics
//! back. Tags arrive as i32 (Int32Array) and are widened to the core's i64; everything else is f64
//! (Float64Array). No allocation crosses back except the small result struct.

use wasm_bindgen::prelude::*;

use crate::gcode;
use crate::metrics;
use crate::parser;
use crate::walk::{walk, Ctx, Steps};

/// The nine simulation metrics, exposed to JS as readonly fields.
#[wasm_bindgen]
pub struct SimMetrics {
    pub total_time_s: f64,
    pub print_time_s: f64,
    pub travel_time_s: f64,
    pub extruding_distance: f64,
    pub travel_distance: f64,
    pub extruded_volume: f64,
    pub filament_length: f64,
    pub segment_count: u32,
    pub max_flow_rate: f64,
}

/// Walk + fold the flattened design to simulation metrics (one pass, in wasm).
#[wasm_bindgen]
pub fn simulate(
    tag: Vec<i32>,
    a: Vec<f64>,
    b: Vec<f64>,
    c: Vec<f64>,
    d: Vec<f64>,
    init: Vec<f64>,
) -> SimMetrics {
    let steps = Steps {
        tag: tag.into_iter().map(|t| t as i64).collect(),
        a,
        b,
        c,
        d,
    };
    let mut ctx = Ctx::from_scalars(&init);
    let r = walk(&steps, &mut ctx);
    let m = metrics::simulate(&r);
    SimMetrics {
        total_time_s: m.total_time_s,
        print_time_s: m.print_time_s,
        travel_time_s: m.travel_time_s,
        extruding_distance: m.extruding_distance,
        travel_distance: m.travel_distance,
        extruded_volume: m.extruded_volume,
        filament_length: m.filament_length,
        segment_count: m.segment_count as u32,
        max_flow_rate: m.max_flow_rate,
    }
}

/// Emit the g-code motion lines from the serialized IR JSON (same engine the Python build uses).
#[wasm_bindgen]
pub fn emit_gcode_moves(
    ir_json: &str,
    relative_e: bool,
    travel_g1_e0: bool,
) -> Result<Vec<String>, JsError> {
    let ir: serde_json::Value = serde_json::from_str(ir_json)
        .map_err(|e| JsError::new(&format!("invalid IR JSON: {e}")))?;
    Ok(gcode::emit_moves(&ir, relative_e, travel_g1_e0))
}

/// Emit a full g-code line list from the serialized IR JSON + a params JSON object.
#[wasm_bindgen]
pub fn emit_gcode(ir_json: &str, params_json: &str) -> Result<Vec<String>, JsError> {
    let ir: serde_json::Value = serde_json::from_str(ir_json)
        .map_err(|e| JsError::new(&format!("invalid IR JSON: {e}")))?;
    let params: serde_json::Value = serde_json::from_str(params_json)
        .map_err(|e| JsError::new(&format!("invalid params JSON: {e}")))?;
    Ok(gcode::emit_gcode(&ir, &gcode::Params::from_json(&params)))
}

/// Parse g-code text into the serialized Toolpath IR JSON (the same engine the Python build uses).
/// `params_json` is a JSON object {flavor, relative_e, e_units, dia_feed, travel_g1_e0}.
#[wasm_bindgen]
pub fn parse_gcode(text: &str, params_json: &str) -> Result<String, JsError> {
    let params: serde_json::Value = serde_json::from_str(params_json)
        .map_err(|e| JsError::new(&format!("invalid params JSON: {e}")))?;
    Ok(parser::parse_gcode(text, &parser::ParseParams::from_json(&params)).to_string())
}
