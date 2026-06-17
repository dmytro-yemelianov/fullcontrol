//! Simulation metrics, folded in Rust over the walk output.
//!
//! Re-implements `fullcontrol.simulate.run.simulate_columnar`'s reduction, but in the same process
//! as the walk and without ever materialising the per-move arrays in Python - the kernel returns
//! only the nine scalars. Sums are sequential here vs numpy's pairwise reduction, so totals can
//! differ in the last bit(s) (the same tolerance the Python columnar simulate already accepts);
//! max_flow_rate is a max reduction and so is order-independent.

use crate::walk::ResolveOut;

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
