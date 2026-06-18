# Toolpath IR — prior-art survey

**Question:** does a *universal intermediate representation / interchange format for additive & CNC
toolpaths* — and the broader idea of *many authoring languages emitting one common toolpath IR consumed
by many backends* — already exist? Should FullControl adopt/align with an existing standard, or harden
its own `fullcontrol/ir/` into a spec (see `docs/ir_spec.md`)?

**Verdict (short):** the general "universal toolpath IR" niche is **genuinely open, but closing** — the
3MF Consortium is actively building a "universal toolpath format for AM," and there is academic work
arguing g-code-as-IR is insufficient. None of it occupies FullControl's specific niche: a hardened,
typed, units-aware, multi-language IR for **algorithmic, arc-native, non-planar, variable-width,
continuous-bead** additive toolpaths with **provenance + invariants + simulate/verify/optimise**. The
recommendation is **harden FullControl's IR into the canonical algorithmic-toolpath IR, and interoperate
(import/export) with — not adopt — 3MF Toolpath, STEP-NC and G-code**, borrowing design ideas from MLIR,
Arrow, glTF and USD.

## Findings — three camps, each missing the target on a different axis

### A. Intent-bearing standards (right philosophy, wrong domain / unadopted)
- **STEP-NC (ISO 14649 / ISO 10303-238 AP238)** — the object-oriented "successor to G-code" that encodes
  *intent* (features, working-steps) plus explicit toolpaths with real curves/arcs. Device-independent
  (EXPRESS). **But:** subtractive/machining-centric; additive data models are research proposals only
  (2018–2025); heavyweight STEP tooling; very low adoption; no native continuous-bead / variable-width
  primitive. The right idea (encode intent + working-step structure); the wrong wire format for us.

### B. Geometry interchange (stops before toolpaths)
- **3MF Slice / Beam Lattice / Volumetric**, **AMF (ISO/ASTM 52915)**, **CLI (Common Layer Interface)** —
  sliced contours / lattices / voxels / mesh. They sit *upstream* of toolpathing (3MF Slice explicitly
  excludes infill/motion/g-code). Useful as **geometry import**, not as a toolpath IR.
- **Code-CAD** — OpenSCAD (`.csg` DSL), CadQuery & build123d (Python), Replicad/JSCAD (JS), all over
  Manifold / Open CASCADE kernels. The ecosystem converged on **shared kernels, not a shared IR**, and
  none reach the toolpath layer — they produce B-rep/mesh. Confirms the "embed in a host language, don't
  invent a surface language" lesson, and that the toolpath IR is unclaimed.

### C. Execution-layer motion IRs (front-end-agnostic but intent-free)
- **LinuxCNC canon (RS274NGC canonical machining functions)** — a clean interpreter→canon split with
  hardware-abstracted `STRAIGHT_FEED`/`ARC_FEED`. A good *motion* IR, but machining vocabulary, planar
  arcs, no additive/bead/variable-width semantics.
- **Klipper move queue (trapq) / GRBL planner** — real-time executors; linear segments only (arcs
  pre-segmented); no design intent.
- **ROS `trajectory_msgs` / MoveIt `RobotTrajectory`** — standardised, multi-language, but sampled
  joint-space waypoints (post-plan trajectories), no geometric/process intent or deposition state.
- **Vendor robot languages (KRL / RAPID / Karel)** — ubiquitous but siloed; no vendor-neutral IR.

### D. The direct competitor / collaboration target
- **3MF Toolpath extension** ⭐ — the 3MF Consortium is explicitly building "a universal toolpath format
  for AM" (multi-axis; DED/FGF/cold-spray), and the **Laser Toolpath** draft already carries
  `beadwidth`/`beadheight` and 6-axis poses. **But** as of this survey it is: (a) unreleased, (b)
  **linear-only — no arc primitives** (curves are tessellated), (c) an XML *sliced / scan-vector* model
  (random-access layers) rather than an *algorithmic design* IR, (d) capped at four modifiable profile
  attributes. It is built bottom-up from PBF scan vectors, not top-down from algorithmic design intent.
  **This is the format to track and interoperate with** — and to push toward arc primitives.

### E. Slicer internal IRs (in-memory, not interchange)
- **CuraEngine** (`LayerPlan`/`ExtrusionLine`/`ExtrusionJunction`) and **PrusaSlicer/Arachne**
  (`ExtrusionEntity`, the variable-width engine behind Bambu/Orca) — genuine per-junction variable width,
  but planar/layer-quantised, polyline-only (arcs are a final-stage g-code post-process via ArcWelder),
  one-way to g-code, and **internal, not a portable spec**.
- **ORNL Slicer 2** — genuinely non-planar + arc-capable for large-scale/multi-axis AM, but the model
  lives inside a monolithic GPL app, consumed as emitted g-code; no embeddable, front-end-agnostic IR.

### F. Design precedents to borrow (not toolpath formats)
- **MLIR** — multi-level dialects + progressive lowering. FullControl's `resolve()` + `passes` is a
  one-level lowering; the layers (design → geometry/path → g-code/3MF) could be formalised as dialects.
- **Apache Arrow** — a rigorously spec'd zero-copy columnar layout. FullControl's `columnar.py` is
  already Arrow-shaped and the Rust-kernel boundary; document it as the binary form.
- **glTF (ISO/IEC 12113)** — human-readable JSON + binary payload + a **named extension mechanism** +
  neutral governance. The model for letting vendor/process features extend a stable core without forking.
- **OpenUSD** — non-destructive **layered composition** (base design + override layers for machine /
  material / process). A direction for separating a design from its machine/material bindings.
- **UCUM / QUDT** — unit-code and dimension ontologies for typed, units-aware, dimension-checkable fields.

### G. Academic validation of the gap
- *Formalizing Linear Motion G-code for Invariant Checking* (OOPSLA 2025, arXiv:2509.00699) — argues
  explicitly that **g-code is an insufficient IR** and motivates a richer, verifiable representation with
  invariants. Directly validates FullControl's IR + verify direction.
- *Implicit Toolpath Generation for Functionally Graded AM* (arXiv:2505.08093) — motivates representing
  toolpaths beyond g-code for graded/variable processes.

## Recommendations

1. **Do not adopt an existing format as the internal IR.** None fit: g-code is the lossy target;
   STEP-NC is subtractive/heavyweight; 3MF Toolpath is linear-only, unreleased and slice-oriented.
2. **Harden `fullcontrol/ir/` into a versioned, documented spec** (done: `docs/ir_spec.md`,
   `SCHEMA_VERSION`/`LATEST_SCHEMA_VERSION`, units + provenance + invariants in v2). This is the novel,
   defensible contribution: the canonical IR for *algorithmic, arc-native, non-planar, variable-width*
   additive toolpaths.
3. **Interoperate, don't adopt:** keep g-code export/import (native arcs ↔ `G2`/`G3`); add 3MF-Toolpath
   export/import as it stabilises (engage the consortium; push for arc primitives); import 3MF/AMF/STL
   geometry for hybrid design; align with STEP-NC only philosophically (carry intent).
4. **Borrow proven IR ideas:** MLIR dialect-lowering, Arrow columnar binary form, glTF JSON+binary+named
   extensions + neutral governance, USD layered composition, UCUM/QUDT units.
5. **Make invariants + provenance first-class** (the verification differentiator no slicer IR offers),
   wired to the existing `validate` / `verify_gcode` rules.

## Key sources

- 3MF Toolpath / Laser Toolpath: <https://3mf.io/spec/> · <https://github.com/3MFConsortium> ·
  <https://github.com/3MFConsortium/spec_lasertoolpath> ·
  <https://www.voxelmatters.com/ai-build-joins-3mf-consortium-to-advance-multi-axis-3d-printing/>
- STEP-NC / ISO 14649 / AP238: <https://www.steptools.com/stds/stepnc/> ·
  <https://en.wikipedia.org/wiki/STEP-NC> · STEP-NC-in-AM review (2025):
  <https://link.springer.com/article/10.1007/s00170-025-15290-8>
- G-code / arcs: <https://en.wikipedia.org/wiki/G-code> · <https://marlinfw.org/docs/gcode/G002-G003.html>
  · <https://www.klipper3d.org/G-Codes.html>
- Slicer IRs: <https://github.com/Ultimaker/CuraEngine> · <https://github.com/prusa3d/PrusaSlicer> ·
  Arachne: <https://help.prusa3d.com/article/arachne-perimeter-generator_352769> ·
  <https://github.com/ORNLSlicer/ORNLSlicer>
- Geometry: CLI <http://hmilch.net/downloads/cli_format.html> · AMF <https://www.iso.org/standard/74640.html>
- Motion: <https://github.com/LinuxCNC/linuxcnc> ·
  <https://docs.ros.org/en/noetic/api/trajectory_msgs/html/msg/JointTrajectory.html>
- Code-CAD: <https://github.com/CadQuery/cadquery> · <https://github.com/gumyr/build123d> ·
  <https://github.com/elalish/manifold> · <https://github.com/openscad/openscad/wiki/CSG-File-Format>
- IR precedents: <https://mlir.llvm.org/> · <https://arrow.apache.org/overview/> ·
  <https://www.khronos.org/gltf/> · <https://openusd.org/release/intro.html>
- Units: <https://qudt.org/> · <https://units-of-measurement.org/>
- Toolpath-IR research: <https://arxiv.org/abs/2509.00699> · <https://arxiv.org/html/2505.08093v2>
- FullControl: <https://github.com/FullControlXYZ/fullcontrol> · Gleadall 2021:
  <https://www.sciencedirect.com/science/article/abs/pii/S2214860421002748>
