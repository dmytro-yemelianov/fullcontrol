//! Rust microkernel: the columnar resolve for the common LINEAR step set.
//!
//! This re-implements `fullcontrol.ir.columnar.resolve_columnar`'s sequential state-walk for a
//! design that has been *flattened* by the Python wrapper (`fullcontrol/ir/kernel.py`) into
//! primitive arrays. The wrapper builds the gcode `State` (so pydantic stays on the Python side),
//! pre-computes per-step derived scalars (extruder volume_to_e, extrusion area/width/height), and
//! hands Rust a flat `(tag, a, b, c)` step stream plus the initial running context.
//!
//! The ABI (struct-of-arrays in, struct-of-arrays out) IS the boundary. Rust never sees a Python
//! object during the walk - only f64/i64 columns - so this is a pure arithmetic fold.
//!
//! Step tags (must match kernel.py):
//!   0 Point:               a=x  b=y  c=z      (NaN component => inherit previous)
//!   1 Extruder:            a=on (-1 none / 0 off / 1 on)  b=volume_to_e (NaN => no change)
//!   2 ExtrusionGeometry:   a=area (NaN => None/0)  b=width (NaN => undefined)  c=height
//!   3 Printer:             a=print_speed (NaN => no change)  b=travel_speed (NaN => no change)
//!   4 StationaryExtrusion: a=volume

use numpy::{IntoPyArray, PyArray1, PyArray2, PyArrayMethods};
use pyo3::prelude::*;

const TAG_POINT: i64 = 0;
const TAG_EXTRUDER: i64 = 1;
const TAG_GEOMETRY: i64 = 2;
const TAG_PRINTER: i64 = 3;
const TAG_STATIONARY: i64 = 4;

/// Result columns returned to Python. Mirrors ColumnarToolpath's per-move columns plus scalars.
struct ResolveOut {
    sx: Vec<f64>,
    sy: Vec<f64>,
    sz: Vec<f64>,
    ex: Vec<f64>,
    ey: Vec<f64>,
    ez: Vec<f64>,
    travel: Vec<bool>,
    speed: Vec<f64>,
    length: Vec<f64>,
    vol: Vec<f64>,
    fil: Vec<f64>,
    src: Vec<i64>,
    wid: Vec<f64>,
    hgt: Vec<f64>,
    material_volume: f64,
    material_filament: f64,
}

#[allow(clippy::too_many_arguments)]
fn resolve(
    tag: &[i64],
    a: &[f64],
    b: &[f64],
    c: &[f64],
    // initial running context (mirrors the gcode State after init):
    init_on: f64, // -1 none / 0 / 1
    init_volume_to_e: f64,
    init_print_speed: f64,
    init_travel_speed: f64,
    init_area: f64, // NaN => None
    init_width: f64,
    init_height: f64,
    init_x: f64,
    init_y: f64,
    init_z: f64,
) -> ResolveOut {
    let n = tag.len();
    // running context
    let mut on: f64 = init_on; // -1/0/1
    let mut volume_to_e = init_volume_to_e;
    let mut print_speed = init_print_speed;
    let mut travel_speed = init_travel_speed;
    let mut area = init_area; // may be NaN (=> None, treated as 0 for volume)
    let mut width = init_width;
    let mut height = init_height;
    let mut px = init_x;
    let mut py = init_y;
    let mut pz = init_z;

    // pre-size columns to the step count (upper bound on number of moves)
    let mut out = ResolveOut {
        sx: Vec::with_capacity(n),
        sy: Vec::with_capacity(n),
        sz: Vec::with_capacity(n),
        ex: Vec::with_capacity(n),
        ey: Vec::with_capacity(n),
        ez: Vec::with_capacity(n),
        travel: Vec::with_capacity(n),
        speed: Vec::with_capacity(n),
        length: Vec::with_capacity(n),
        vol: Vec::with_capacity(n),
        fil: Vec::with_capacity(n),
        src: Vec::with_capacity(n),
        wid: Vec::with_capacity(n),
        hgt: Vec::with_capacity(n),
        material_volume: 0.0,
        material_filament: 0.0,
    };

    let volume_to_e_or_0 = |v: f64| if v.is_nan() { 0.0 } else { v };

    for i in 0..n {
        match tag[i] {
            TAG_POINT => {
                let x0 = px;
                let y0 = py;
                let z0 = pz;
                let sxv = a[i];
                let syv = b[i];
                let szv = c[i];
                // dx/dy/dz: 0 if either endpoint undefined (NaN), else delta
                let dx = if x0.is_nan() || sxv.is_nan() { 0.0 } else { sxv - x0 };
                let dy = if y0.is_nan() || syv.is_nan() { 0.0 } else { syv - y0 };
                let dz = if z0.is_nan() || szv.is_nan() { 0.0 } else { szv - z0 };
                let extruding = on > 0.5;
                // update_from: only non-None (non-NaN) axes propagate
                if !sxv.is_nan() {
                    px = sxv;
                }
                if !syv.is_nan() {
                    py = syv;
                }
                if !szv.is_nan() {
                    pz = szv;
                }
                let x1 = px;
                let y1 = py;
                let z1 = pz;
                // "any axis changed -> a move". Compare with NaN-aware equality (NaN==NaN here
                // means 'still undefined', i.e. unchanged).
                let changed = !same(x0, x1) || !same(y0, y1) || !same(z0, z1);
                if changed {
                    let ln = (dx * dx + dy * dy + dz * dz).sqrt();
                    let spd = if extruding { print_speed } else { travel_speed };
                    let area_or_0 = if area.is_nan() { 0.0 } else { area };
                    let v = if extruding { ln * area_or_0 } else { 0.0 };
                    out.sx.push(x0);
                    out.sy.push(y0);
                    out.sz.push(z0);
                    out.ex.push(x1);
                    out.ey.push(y1);
                    out.ez.push(z1);
                    out.travel.push(!extruding);
                    out.speed.push(spd);
                    out.length.push(ln);
                    out.vol.push(v);
                    out.fil.push(v * volume_to_e_or_0(volume_to_e));
                    out.src.push(i as i64);
                    out.wid.push(width);
                    out.hgt.push(height);
                }
            }
            TAG_STATIONARY => {
                let volume = a[i];
                out.material_volume += volume;
                out.material_filament += volume * volume_to_e_or_0(volume_to_e);
            }
            TAG_EXTRUDER => {
                let new_on = a[i];
                if new_on >= -0.5 {
                    // -1 means None (no change); 0/1 update
                    on = new_on;
                }
                if !b[i].is_nan() {
                    volume_to_e = b[i];
                }
            }
            TAG_GEOMETRY => {
                // area/width/height already resolved in Python (post update_from + update_area).
                area = a[i]; // may be NaN => None
                width = b[i];
                height = c[i];
            }
            TAG_PRINTER => {
                if !a[i].is_nan() {
                    print_speed = a[i];
                }
                if !b[i].is_nan() {
                    travel_speed = b[i];
                }
            }
            _ => {}
        }
    }

    out
}

/// NaN-aware "are these the same coordinate" (treats NaN==NaN, i.e. both undefined).
#[inline]
fn same(p: f64, q: f64) -> bool {
    (p.is_nan() && q.is_nan()) || p == q
}

/// PyO3 entry point. Takes the flattened step columns + initial context, returns a tuple of
/// numpy arrays + the two material scalars, ready for the wrapper to pack into a ColumnarToolpath.
#[allow(clippy::too_many_arguments)]
#[pyfunction]
fn resolve_columnar<'py>(
    py: Python<'py>,
    tag: Vec<i64>,
    a: Vec<f64>,
    b: Vec<f64>,
    c: Vec<f64>,
    init_on: f64,
    init_volume_to_e: f64,
    init_print_speed: f64,
    init_travel_speed: f64,
    init_area: f64,
    init_width: f64,
    init_height: f64,
    init_x: f64,
    init_y: f64,
    init_z: f64,
) -> PyResult<(
    Bound<'py, PyArray2<f64>>, // start (N,3)
    Bound<'py, PyArray2<f64>>, // end (N,3)
    Bound<'py, PyArray1<bool>>,
    Bound<'py, PyArray1<f64>>, // speed
    Bound<'py, PyArray1<f64>>, // length
    Bound<'py, PyArray1<f64>>, // deposited_volume
    Bound<'py, PyArray1<f64>>, // filament_length
    Bound<'py, PyArray1<i64>>, // source_index
    Bound<'py, PyArray1<f64>>, // width
    Bound<'py, PyArray1<f64>>, // height
    f64,                       // material_volume
    f64,                       // material_filament
)> {
    let r = py.allow_threads(|| {
        resolve(
            &tag, &a, &b, &c, init_on, init_volume_to_e, init_print_speed, init_travel_speed,
            init_area, init_width, init_height, init_x, init_y, init_z,
        )
    });

    let n = r.travel.len();
    // build (N,3) start/end as flat row-major then reshape
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

#[pymodule]
fn fullcontrol_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(resolve_columnar, m)?)?;
    Ok(())
}
