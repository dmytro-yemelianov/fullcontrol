# FullControl — Architectural & In-Place Improvement Plan

Companion to `CODE_REVIEW.md` (bug-level findings, mostly fixed on branch
`fix/high-severity-review-findings`). This document is forward-looking: how to
improve the *structure* of the codebase. Two tracks — **In-place** (low-risk,
incremental, no public-API change) and **Architectural** (bigger refactors) —
followed by a sequenced roadmap.

Guiding constraints assumed throughout (confirm before executing):
- **Keep the user-facing API stable**: `import fullcontrol as fc`, `fc.Point(...)`,
  `fc.transform(steps, 'gcode'|'plot', controls)`, and `printer_name` strings
  (`"ender_3"`, `"Cura/…"`, `"Community/…"`) must keep working unchanged.
- **Land a safety net (CI + unit tests) before any structural refactor.**
- Backward-incompatible cleanups are allowed only behind shims or with a version bump.

---

## Track 1 — In-place improvements (low risk, do first)

These need no architecture change and are individually shippable. Effort: S = <½ day, M = ~1 day.

### Infrastructure (highest value/effort ratio)
| ID | Change | Why | Effort | Risk |
|----|--------|-----|--------|------|
| I1 | **GitHub Actions CI**: matrix py3.10–3.13, `pip install -e .[test]`, `pytest tests/unit -q`, plus `python -m build` | No CI exists today (`.github/workflows/` absent); the 19-test unit suite runs in 0.1s but nothing enforces it | S | none |
| I2 | **Declare deps**: `[project.optional-dependencies]` test=`[pytest]`, viz=`[kaleido]`, dev=test+viz+ruff; pin floors `pydantic>=2,<3`, `numpy>=1.24`, `plotly>=5` | Test/viz deps undeclared; runtime deps unpinned (resolver could pull pydantic v1 and break imports) | S | none |
| I3 | **Make `tests/CICD_test.py` non-interactive**: drop `input()` (L43), use `sys.executable` not `'python'` (L27), sort sets/dicts before diffing, exit non-zero on real diffs, gate the kaleido image step behind a flag | Harness can't run unattended; `'python'` isn't on modern PATHs; set-ordering produces false-positive diffs | M | low |
| I4 | **ruff config** (`[tool.ruff]`, lint-only F/E/I to start) + a lint CI job | No lint/format config; ~33% of defs have return annotations | S | none |

### Code cleanups (mechanical, scoped)
| ID | Change | File(s) | Effort |
|----|--------|---------|--------|
| I5 | Remove stray `from pydantic import root_validator` (unused v1 API, breaks under pydantic v3) | `gcode/extrusion_classes.py:8` | S |
| I6 | Dedupe `ender_5_plus.py` → delegate to `ender_3.set_up()` + patch (it differs by 1 line) | `devices/.../ender_5_plus.py` | S |
| I7 | Replace index-based step patching with named-marker helpers (`replace_step_by_marker`/`insert_after_marker`) | `cr_10.py:11`, `toolchanger_T1/2/3.py`, `prusa_i3.py:42-44` | M |
| I8 | Unify split temp keys (`enclosure_temp` vs `chamber_temp`) on one canonical key + alias | `base_settings.py:9`, `voron_zero.py:13` | S |
| I9 | Extract a `fmt(v, dp=6)` gcode-number helper; replace the `f'{v:.6f}'.rstrip('0').rstrip('.')` idiom duplicated across `gcode/point.py`, `extrusion_classes.py`, `printer.py`, and the lab copies | several | S |
| I10 | Guard the processing loop: wrap per-step dispatch in `try/except` with `f"step {i} ({type(step).__name__})"` context; add a max-iteration sentinel | `gcode/steps2gcode.py:28`, `visualize/steps2visualization.py:24` | S |
| I11 | Fix mutable Pydantic defaults (`gcode=[]`, `paths=[]`, `annotations=[]`) → `Field(default_factory=list)` | `gcode/state.py:40`, `visualize/plot_data.py:33,35` | S |
| I12 | Replace blanket `except: pass` with specific None/attr checks | `extrusion_classes.py:31-32,134` | S |
| I13 | Guard `GcodeComment` against empty `state.gcode[-1]` | `annotations.py:28` | S |
| I14 | Unify `GcodeControls`/`PlotControls` onto `BaseModelPlus` (currently plain `BaseModel`, so they silently swallow unknown kwargs and lack dict-access) | `gcode/controls.py:6`, `visualize/controls.py:6` | S* |

\* I14 *tightens* validation (unknown kwargs would start raising) — technically a behavior change; ship behind the next minor version and scan examples for stray kwargs first.

---

## Track 2 — Architectural improvements

Bigger refactors. Each lists the problem, the proposal, backward-compat strategy, and effort (days). All assume CI + a snapshot/MRO test exist first.

### A1 — Drop pydantic v1 support
**Problem:** `base.py:50-69` carries a `__version__`-branched v1/v2 shim; the v1 path is untested and `setup.py`/`pyproject` don't bound pydantic. The stray v1 `root_validator` import (I5) is a v3 landmine.
**Proposal:** delete the v1 branch, keep only `model_validator`; pin `pydantic>=2,<3`.
**Compat:** v1 users break — but the v1 path is already untested and effectively nobody is on it. **Effort:** ~0.5d. *Prerequisite for a clean object-model refactor.*

### A2 — Auto-generate the combined classes from a registry
**Problem:** `combinations/gcode_and_visualize/classes.py` is ~250 lines of hand-written `class Point(gc.Point, vis.Point): pass` glue with re-typed docstrings; the authors themselves flag it should be automated (`classes.py:10-13`). Adding a step type silently fails until this file is also edited; docstrings live in 3 places and already drift.
**Proposal:** drive a `SPECS = {name: capabilities}` registry; synthesize each combined class via `type(name, bases, {...})`. The gcode-only/viz-only/dual decision becomes data, not hand-coded inheritance; `PassGcode`/`PassVisualize` selection is automatic.
**Compat:** `fc.Point` keeps identical name/MRO/fields — lock with an MRO+field-set snapshot test generated from today's classes. **Effort:** ~1d.

### A3 — Renderer/visitor separation (pure-data classes + backend emitters)
**Problem (core coupling):** every step class is a data model that *also* knows how to emit gcode **and** plot itself (`class Point(gc.Point, vis.Point)`). This forces a dual `.gcode()`/`.visualize()` method on every class, makes emission impossible to unit-test without booting a full `State` (which imports a device module and builds primers in `__init__`), and means a 3rd output format multiplies rather than adds.
**Proposal:** make step classes pure data; move emitters into backend modules dispatched by `functools.singledispatch` (`@render.register(Point)`). The loop calls `renderer.render(step, state)` instead of `step.gcode(state)`. `classes.py` collapses to plain data classes; the `Pass*` stubs disappear.
**Compat:** user API (`fc.Point`, `fc.transform`) unchanged; `export/import_design` (class-name keyed) still valid. Breaks any code calling `step.gcode()` directly (the lab forks — addressed by A4). **Effort:** ~1–2 weeks. *Synergistic with A2; do A2 first.*

### A4 — Pluggable backend registry + one shared pipeline driver
**Problem:** the lab backends don't extend the pipeline — they **fork** it. `lab/.../multiaxis/gcode/XYZB/steps2gcode.py` is a near-verbatim copy of the core while-loop; `lab/fullcontrol/transform.py` is a parallel `transform` with its own result types; the laser format is implemented by **regex-stripping Z/E** from generated gcode.
**Proposal:** `BACKENDS = {'gcode':…, 'plot':…, 'multiaxis':…, 'controlcode':…}`; extract the shared `while state.i < len(steps)` loop into one `run_pipeline(steps, state, backend)`. New backends register a renderer instead of copying the tree.
**Compat:** `transform('gcode'|'plot')` unchanged; lab `transform` becomes thin registration. **Effort:** ~medium, after A3.

### A5 — Device `Profile` base class with named step hooks + unified loader
**Problem:** three incompatible printer systems (singletool Python `set_up()`, community_minimal JSON+template, cura JSON+template) dispatched by string-prefix slicing (`state.py:56`, `import_printer.py:90-91`); derived profiles patch start-procedures by **positional index** (`cr_10`, `prusa_i3`, toolchangers); ~25-line boilerplate repeated across 17 profiles.
**Proposal:** one `Profile` model holding a unified settings schema + an **ordered, named** procedure spec; derived printers override by name (`replace_step("max_dims", …)`, `insert_after("heat_nozzle", …)`). A single registry resolves `printer_name` → `Profile` across all three sources (keep `Cura/`/`Community/` as namespaces).
**Compat:** `printer_name` strings preserved via the registry; 662 cura data-dicts reused unchanged. **Effort:** ~2–4d. Removes ~300+ LOC of singletool duplication and all index-patching.

### A6 — Parametric multiaxis stack with pluggable kinematics
**Problem:** `lab/.../multiaxis/gcode/{XYZB,XYZBC,XYZC0B1}/` is ~80% copy-paste (738 LOC; `printer.py`/`steps2gcode.py` differ by 2–4 lines). Only the inverse-kinematics math genuinely differs. Every fix must be made 3×.
**Proposal:** one shared `state.py`/`printer.py`/`controls.py`/`steps2gcode.py` + a pluggable `Kinematics` object per machine config; the gcode formatter iterates a configured axis list. **This is the right moment to fix the still-open HIGH-5 XYZBC `bc_intercept` kinematics bug, with unit tests.**
**Compat:** lab import paths change, but lab is explicitly experimental; provide re-export shims. **Effort:** ~medium. Deletes ~450 LOC.

---

## Sequenced roadmap

```
Phase 0  SAFETY NET + QUICK WINS  (in-place, ~2 days, no API change)
  I1 CI · I2 deps · I3 non-interactive harness · I4 ruff
  I5 root_validator · I6 ender_5_plus · I9 fmt helper
  I10 loop guard · I11 mutable defaults · I12 except · I13 GcodeComment
  → Establishes the regression net every later phase depends on.

Phase 1  FOUNDATION  (~2–3 days)
  A1 drop pydantic v1 · I14 unify controls on BaseModelPlus
  I7 named-step markers · I8 temp keys
  Extract device-init out of State.__init__  → makes emission testable
  → Grow tests/unit into real gcode-emission + geometry coverage.

Phase 2  OBJECT MODEL  (~1–2 days)
  A2 auto-generate combined classes (+ MRO/field snapshot test)

Phase 3  PIPELINE  (~2 weeks)
  A3 renderer/visitor separation
  A4 pluggable backend registry + shared driver (folds in lab backends)

Phase 4  DEVICES  (~1 week)
  A5 Profile base + named hooks + unified loader
  A6 parametric multiaxis + pluggable kinematics (fixes HIGH-5)
```

Each phase is independently valuable and leaves the tree releasable. Phases 0–1
are pure wins with negligible risk; Phases 2–4 are where the structural payoff is
but should only start once CI + emission-level tests (Phases 0–1) can catch
regressions.

## Highest-leverage picks (if doing only a few things)
1. **I1 + I3 (CI on the existing suite + non-interactive harness).** Biggest confidence gain for least effort.
2. **A3 (renderer/visitor separation).** Removes the central coupling; unlocks testability and new backends; everything else gets easier after.
3. **A5/A6 (device Profile + parametric multiaxis).** Where the duplicated-maintenance cost actually lives (17 profiles + 3× multiaxis), and the path to finally fixing HIGH-5.
