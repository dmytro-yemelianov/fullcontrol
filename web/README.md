# Browser demos

Three complementary ways FullControl runs in the browser:

- **`index.html`** — the **polished demo** (below): a parametric toolpath designer. Pick a design,
  drag parameter sliders, watch the toolpath regenerate, see live print metrics, and download a
  full printable g-code file. Geometry is authored in JavaScript; the FullControl **Rust engine runs
  in WebAssembly** (`simulate_from_ir`, `emit_gcode`). Zero server.
- **`viewer.html`** — the original single-design (twisted-polygon-vase) viewer, kept for reference;
  it also parses & simulates an uploaded `.gcode` file entirely client-side.
- **`playground/`** — the **whole library** running client-side via **Pyodide** (CPython in WASM).
  Edit a FullControl design in Python, click Generate, and real g-code comes back — `fc.transform`
  runs in the browser, no server. The complete library (all backends, all device profiles).

## The polished demo (`index.html`)

A fully client-side, deployable demo. Files:

```
web/                     ← Cloudflare Pages output root
  index.html             the demo: design picker, sliders, 3D viewer, metrics, g-code download
  designs.js             the design catalogue — vanilla JS that builds the serialized v2 Toolpath IR
  viewer.html            the original single-design viewer (+ .gcode upload/analyse)
  pkg/                   generated wasm: fullcontrol_kernel.js + fullcontrol_kernel_bg.wasm
  playground/            the Pyodide "whole library" page (+ committed wheel)
  _headers               Pages headers (application/wasm MIME, caching, security)
  _redirects             friendly aliases (/demo, /viewer, /playground)
  build.sh               rebuild pkg/ from rust_kernel (cargo + wasm-bindgen)
../wrangler.toml         Pages project config (pages_build_output_dir = "web")
```

**Designs** (authored in `designs.js`, all in vanilla JS — no build step): spiral vase, fluted vase,
arc-scalloped vase (native `fc.Arc` G2/G3 moves), twisted polygon vase, corrugated snake-mode wall,
spirograph cup. Each builds the **serialized Toolpath IR (schema v2)** — the exact JSON the wasm
kernel and `fullcontrol.ir.from_dict` consume — so the IR is interchangeable with any FullControl
front-end ("many front-ends, one IR"). The viewer expands arcs from their `arc_points`; metrics come
straight from `simulate_from_ir`; the **Download g-code** button wraps the design with start/heat/
fan/end procedures and lets `emit_gcode` produce a complete printable file (native arcs emit as real
G2/G3). Two invariants (monotonic layer-z, non-negative extrusion) are checked in JS and shown as a
✓/⚠ badge.

#### Render modes — Lines | Realistic

A **Render** toggle (top-right of the viewer) switches between two views of the same toolpath:

- **Lines** (default, fast) — the existing vertex-coloured polyline: travels dimmed, height-ramp
  colour. Instant; best for reading the path.
- **Realistic / as-printed** — each *extruding* segment is rendered as a solid deposited bead, like a
  slicer preview. Built as a single **`InstancedMesh`** of oriented boxes (one instance per move,
  scaled `width × height × length`, slightly wider-than-tall for the FFF stadium read, overlapped a
  touch end-to-end so consecutive beads/layers fuse). One draw call keeps the default vase's ~17k
  segments fully interactive (120 fps in testing). Lighting is a camera-following key
  `DirectionalLight` (with a soft contact shadow onto a bed plane) + `HemisphereLight` + ambient +
  a subtle `RoomEnvironment` IBL via `PMREMGenerator` for plastic sheen; ACES tone mapping. Layer
  grooves are accented with **SSAO** (`EffectComposer` + `SSAOPass` + `OutputPass`); if that ever
  fails to load over the CDN importmap it falls back silently to lighting + bead overlap only.
  Switching modes (or designs) disposes the old geometry/material — no leaks. A **▶ Print** button
  grows the beads in deposition order over a few seconds.

This adds these `three/addons/...` modules to the importmap: `environments/RoomEnvironment.js`,
`postprocessing/EffectComposer.js`, `postprocessing/RenderPass.js`, `postprocessing/SSAOPass.js`,
`postprocessing/OutputPass.js` — all still CDN-loaded (no build step).

### Deploy to Cloudflare Pages

After a one-time `npx wrangler login`, one command publishes the static site:

```bash
npx wrangler pages deploy web --project-name fullcontrol-demo
```

(`wrangler.toml` at the repo root sets `pages_build_output_dir = "web"`. The `pkg/` wasm and the
Pyodide wheel are committed, so there is **no build step**. `web/_headers` serves `.wasm` as
`application/wasm`. three.js is loaded from the unpkg CDN via an importmap.)

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
cd web && python3 -m http.server 8787   # then open http://localhost:8787
```

You can also preview through Wrangler (applies `_headers`/`_redirects` like production):

```bash
npx wrangler pages dev web
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
