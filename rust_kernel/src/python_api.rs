//! PyO3 binding for the microkernel.
//!
//! Two entry points, both running the single sequential walk in `walk.rs`:
//!   - `resolve_columnar` returns the resolved per-move columns (for the columnar IR),
//!   - `simulate` folds the same walk into the nine SimulationResult scalars (no big arrays cross
//!     back to Python - the compute stays in Rust).
//!
//! The flattened-step ABI lives in `kernel.py`. Each entry point takes the design as a `tag`
//! column plus a `payload` tuple of the four f64 columns (a, b, c, d), and the initial running
//! context as a 10-element `init` vector (order matches kernel.py `_init_args`).

use numpy::{IntoPyArray, PyArray1, PyArray2, PyArrayMethods};
use pyo3::prelude::*;

use crate::metrics;
use crate::walk::{walk, Ctx, ResolveOut, Steps};

/// The four f64 step columns (a, b, c, d), passed from Python as one tuple.
type Payload = (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>);

/// The columnar resolve result handed back to Python: start/end (N,3), the per-move columns, and
/// the two stationary-material scalars.
type Columns<'py> = (
    Bound<'py, PyArray2<f64>>,
    Bound<'py, PyArray2<f64>>,
    Bound<'py, PyArray1<bool>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<f64>>,
    f64,
    f64,
);

/// The nine SimulationResult scalars handed back to Python (segment_count is the i64).
type Metrics = (f64, f64, f64, f64, f64, f64, f64, i64, f64);

fn steps_from(tag: Vec<i64>, payload: Payload) -> Steps {
    let (a, b, c, d) = payload;
    Steps { tag, a, b, c, d }
}

/// Resolve the flattened design to columnar arrays (drop-in for `resolve_columnar`'s output).
#[pyfunction]
fn resolve_columnar(
    py: Python<'_>,
    tag: Vec<i64>,
    payload: Payload,
    init: Vec<f64>,
) -> PyResult<Columns<'_>> {
    let steps = steps_from(tag, payload);
    let r: ResolveOut = py.allow_threads(|| {
        let mut ctx = Ctx::from_scalars(&init);
        walk(&steps, &mut ctx)
    });

    let n = r.travel.len();
    let mut start_flat = Vec::with_capacity(n * 3);
    let mut end_flat = Vec::with_capacity(n * 3);
    for i in 0..n {
        start_flat.push(r.sx[i]);
        start_flat.push(r.sy[i]);
        start_flat.push(r.sz[i]);
        end_flat.push(r.ex[i]);
        end_flat.push(r.ey[i]);
        end_flat.push(r.ez[i]);
    }
    let start = PyArray1::from_vec(py, start_flat).reshape([n, 3])?;
    let end = PyArray1::from_vec(py, end_flat).reshape([n, 3])?;

    Ok((
        start,
        end,
        r.travel.into_pyarray(py),
        r.speed.into_pyarray(py),
        r.length.into_pyarray(py),
        r.vol.into_pyarray(py),
        r.fil.into_pyarray(py),
        r.src.into_pyarray(py),
        r.wid.into_pyarray(py),
        r.hgt.into_pyarray(py),
        r.material_volume,
        r.material_filament,
    ))
}

/// Walk + fold to the nine simulation metrics in one Rust pass (no per-move arrays returned).
#[pyfunction]
fn simulate(py: Python<'_>, tag: Vec<i64>, payload: Payload, init: Vec<f64>) -> Metrics {
    let steps = steps_from(tag, payload);
    let m = py.allow_threads(|| {
        let mut ctx = Ctx::from_scalars(&init);
        let r = walk(&steps, &mut ctx);
        metrics::simulate(&r)
    });
    (
        m.total_time_s,
        m.print_time_s,
        m.travel_time_s,
        m.extruding_distance,
        m.travel_distance,
        m.extruded_volume,
        m.filament_length,
        m.segment_count,
        m.max_flow_rate,
    )
}

#[pymodule]
fn fullcontrol_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(resolve_columnar, m)?)?;
    m.add_function(wrap_pyfunction!(simulate, m)?)?;
    Ok(())
}
