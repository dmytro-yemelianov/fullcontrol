//! wasm-bindgen binding for the microkernel - the same compute core, callable from JavaScript.
//!
//! The browser builds the flattened-step columns (tag + a/b/c/d) and the 10-element init context
//! exactly as `kernel.py` does on the Python side, then calls `simulate` to get the print metrics
//! back. Tags arrive as i32 (Int32Array) and are widened to the core's i64; everything else is f64
//! (Float64Array). No allocation crosses back except the small result struct.

use wasm_bindgen::prelude::*;

use crate::metrics;
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
