# Browser demos

Two complementary ways FullControl runs in the browser:

- **`playground/`** — the **whole library** running client-side via **Pyodide** (CPython in WASM).
  Edit a FullControl design in Python, click Generate, and real g-code comes back — `fc.transform`
  runs in the browser, no server. The complete library (all backends, all 695 device profiles).
- **`index.html`** (below) — a **native-WASM** demo: geometry in JS, print metrics from the Rust
  kernel compiled to wasm. Tiny and fast, but only the simulate path.

## Pyodide playground (`playground/`)

`playground/index.html` loads Pyodide from a CDN, `micropip`-installs numpy + pydantic, then installs
the committed FullControl wheel (`deps=False`, so plotly is skipped — g-code/simulate/validate don't
need it). The editor's Python defines `steps`; the page runs `fc.transform(steps, 'gcode')` plus a
simulation and shows the g-code + stats + a download link. Rebuild the wheel with
`bash playground/build-wheel.sh` after changing the library.

Why it works with no porting: FullControl is pure Python and its only runtime deps (numpy, pydantic,
plotly) all run under Pyodide; the Rust kernel extension isn't loadable there, so simulate uses its
pure-Python fallback automatically. Deploys to Cloudflare Pages exactly like the rest of `web/` (the
wheel is committed, so no build step) — first load pulls ~10 MB of Pyodide, cached thereafter.

# Live WASM design viewer

A fully client-side demo: a twisted-polygon-vase designer where the geometry is generated in
JavaScript and the **print metrics (time / material / peak flow) are computed by the FullControl
Rust kernel compiled to WebAssembly**, running in the browser. Drag a slider → the toolpath
regenerates and the kernel re-simulates it in well under a millisecond. three.js draws it.

```
web/
  index.html          the viewer + UI (three.js from CDN, imports ./pkg)
  pkg/                generated: fullcontrol_kernel.js + fullcontrol_kernel_bg.wasm
  build.sh            rebuild pkg/ from rust_kernel (cargo + wasm-bindgen)
```

## Run locally

It must be served over HTTP (ES modules + wasm don't load from `file://`):

```bash
cd web && python -m http.server 8000   # then open http://localhost:8000
```

## How the kernel gets into the browser

The kernel's compute core (`rust_kernel/src/walk.rs` + `metrics.rs`) is pure Rust over plain slices
— no PyO3, no numpy — so the same code that powers the Python extension compiles to wasm. The crate
exposes two binding front-ends behind Cargo features:

- `python` (default) → PyO3 extension, built by maturin / `pip install ./rust_kernel`
- `wasm` → `wasm-bindgen` module (`rust_kernel/src/wasm_api.rs`), built by `web/build.sh`

`index.html` builds the flattened step columns + the init context exactly as the Python wrapper
(`fullcontrol/ir/kernel.py`) does, then calls the wasm `simulate(tag, a, b, c, d, init)`.

## Deploy to Cloudflare Pages (free)

This is a static site — no server code — so it drops straight onto Cloudflare Pages' free tier:

1. Push this repo to GitHub (already done).
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** → pick the repo.
3. Build settings: **Framework preset = None**, **Build command = (empty)**, **Build output
   directory = `web`**. (The `pkg/` wasm is committed, so no build step is needed.)
4. Deploy. Cloudflare serves `.wasm` with the correct `application/wasm` MIME type automatically.

To build the wasm in CI instead of committing it, set the build command to
`bash web/build.sh` and add the Rust toolchain + `wasm-bindgen-cli` to the build image.

### What it can and can't do client-side
- **Works fully client-side:** the parametric vase (geometry in JS) and all print metrics (the wasm
  kernel). No network calls after the page + wasm load.
- **Not in the browser yet:** arbitrary FullControl designs and the gcode/printer-profile resolution
  still live in Python. The kernel only resolves/simulates a *flattened* design; design authoring
  (the `examples/` functions, primer/start-end procedures, printer config) would each need a JS/Rust
  port to run client-side. This demo ports one design (the vase) to JS to show the pattern.
