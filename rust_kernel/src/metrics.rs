//! Simulation metrics, folded in Rust over the walk output.
//!
//! Re-implements `fullcontrol.simulate.run.simulate_columnar`'s reduction, but in the same process
//! as the walk and without ever materialising the per-move arrays in Python - the kernel returns
//! only the nine scalars. Sums are sequential here vs numpy's pairwise reduction, so totals can
//! differ in the last bit(s) (the same tolerance the Python columnar simulate already accepts);
//! max_flow_rate is a max reduction and so is order-independent.

use crate::walk::ResolveOut;
use serde_json::Value;

/// The nine SimulationResult fields, in the order kernel.py unpacks them.
pub struct Metrics {
    pub total_time_s: f64,
    pub print_time_s: f64,
    pub travel_time_s: f64,
    pub extruding_distance: f64,
    pub travel_distance: f64,
    pub extruded_volume: f64,
    pub filament_length: f64,
    pub segment_count: i64,
    pub max_flow_rate: f64,
}

impl Metrics {
    fn zeroed() -> Metrics {
        Metrics {
            total_time_s: 0.0,
            print_time_s: 0.0,
            travel_time_s: 0.0,
            extruding_distance: 0.0,
            travel_distance: 0.0,
            extruded_volume: 0.0,
            filament_length: 0.0,
            segment_count: 0,
            max_flow_rate: 0.0,
        }
    }
}

/// Fold the serialized Toolpath IR JSON into the nine simulation metrics.
///
/// This is the byte-for-byte equivalent of `fullcontrol.simulate.run.simulate_from_ir`: a stateless
/// fold over the IR event stream (`segment` and `material` events; every other event is ignored).
/// It lets the wasm/PyO3 sides simulate straight from a parsed IR document - the same JSON the
/// `parse_gcode` entry point produces - with no Python in the loop. Sums are sequential here, exactly
/// as the Python object fold does them, so totals match it bit-for-bit (the numpy columnar path may
/// differ in the last bit(s) by its pairwise reduction; `max_flow_rate` is a max and so is identical).
pub fn simulate_from_ir(ir: &Value) -> Metrics {
    let mut m = Metrics::zeroed();
    let empty: Vec<Value> = Vec::new();
    let events = ir
        .get("events")
        .and_then(|e| e.as_array())
        .unwrap_or(&empty);
    for ev in events {
        match ev.get("k").and_then(|k| k.as_str()) {
            Some("segment") => {
                let speed = ev["speed"].as_f64().unwrap_or(0.0);
                let length = ev["length"].as_f64().unwrap_or(0.0);
                if speed != 0.0 && length > 0.0 {
                    let t = length / speed * 60.0; // mm / (mm/min) -> minutes -> seconds
                    m.total_time_s += t;
                    if !ev["travel"].as_bool().unwrap_or(false) {
                        let vol = ev["deposited_volume"].as_f64().unwrap_or(0.0);
                        m.print_time_s += t;
                        m.extruding_distance += length;
                        m.extruded_volume += vol;
                        m.filament_length += ev["filament_length"].as_f64().unwrap_or(0.0);
                        if t > 0.0 {
                            let flow = vol / t;
                            if flow > m.max_flow_rate {
                                m.max_flow_rate = flow;
                            }
                        }
                    } else {
                        m.travel_time_s += t;
                        m.travel_distance += length;
                    }
                    m.segment_count += 1;
                }
            }
            Some("material") => {
                m.extruded_volume += ev["deposited_volume"].as_f64().unwrap_or(0.0);
                m.filament_length += ev["filament_length"].as_f64().unwrap_or(0.0);
            }
            _ => {}
        }
    }
    m
}

pub fn simulate(r: &ResolveOut) -> Metrics {
    let mut m = Metrics {
        total_time_s: 0.0,
        print_time_s: 0.0,
        travel_time_s: 0.0,
        extruding_distance: 0.0,
        travel_distance: 0.0,
        extruded_volume: 0.0,
        filament_length: 0.0,
        segment_count: 0,
        max_flow_rate: 0.0,
    };
    let n = r.travel.len();
    for i in 0..n {
        let speed = r.speed[i];
        let length = r.length[i];
        if speed != 0.0 && length > 0.0 {
            let t = length / speed * 60.0; // mm / (mm/min) -> minutes -> seconds
            m.total_time_s += t;
            if !r.travel[i] {
                m.print_time_s += t;
                m.extruding_distance += length;
                m.extruded_volume += r.vol[i];
                m.filament_length += r.fil[i];
                if t > 0.0 {
                    let flow = r.vol[i] / t;
                    if flow > m.max_flow_rate {
                        m.max_flow_rate = flow;
                    }
                }
            } else {
                m.travel_time_s += t;
                m.travel_distance += length;
            }
            m.segment_count += 1;
        }
    }
    // stationary material contributes to totals regardless of any move
    m.extruded_volume += r.material_volume;
    m.filament_length += r.material_filament;
    m
}
