//! FullControl Rust microkernel.
//!
//! The compute core (`walk.rs` + `metrics.rs`) is pure Rust over plain structs and slices - no
//! binding library - so it compiles unchanged for any target. Two binding front-ends sit on top,
//! selected by Cargo feature:
//!   - `python` (default): a PyO3 extension module (built by maturin / `pip install ./rust_kernel`),
//!   - `wasm`: a wasm-bindgen module for the browser (same core, exposed to JavaScript).

mod gcode;
mod metrics;
mod walk;

#[cfg(feature = "python")]
mod python_api;

#[cfg(feature = "wasm")]
mod wasm_api;
