# FullControl — Whole-Codebase Review

Review of `FullControlXYZ/fullcontrol` @ `master` (commit `9a90c40`). Scope: the core
`fullcontrol/` package and experimental `lab/` tree (~17k LOC). Findings are grouped by
severity; locations are `file:line`. Items marked ✅ were spot-verified against source.

---

## HIGH — correctness / security

1. **Arbitrary code execution via `eval()` on gcode templates** ✅
   `fullcontrol/gcode/import_printer.py:32` — `eval(variable)` runs on every `{…}` term
   extracted from a printer's start/end gcode string. A malicious or careless printer
   profile / user override (e.g. `{__import__("os").system("…")}`) executes arbitrary
   Python at transform time. Replace with a whitelisted lookup into `data`.

2. **`arcXY_3pt` angle-normalization loop is a no-op → wrong arcs** ✅
   `fullcontrol/geometry/arcs.py:87-93` — `for angle in [...]: while angle < 0: angle += 2*pi`
   mutates only the loop variable; `start/mid/end_angle` are never reassigned. The `ccw`
   test and `arc_angle` formula then run on raw `atan2` output `[-π, π]`, producing wrong
   sweep direction/magnitude whenever points straddle the `0`/`±π` boundary.
   Fix: `start_angle, mid_angle, end_angle = [a % (2*pi) for a in (...)]`.

3. **Scientific-notation E/coordinate values that firmware rejects** ✅
   - `fullcontrol/gcode/extrusion_classes.py:40` — `StationaryExtrusion` uses `:.6`
     (6 sig-figs) instead of `:.6f`+strip like `e_gcode` (lines 118/122). Small/large values
     emit e.g. `E1.2e-05`.
   - `lab/.../multiaxis/gcode/XYZB|XYZBC|XYZC0B1/point.py` — X/Y/Z formatted `:.6`; a value
     ≥100000 emits `1.23457e+03`. Only the XYZB `B` axis uses correct `:.6f`.
   Standardize on fixed-decimal formatting everywhere.

4. **`custom` device emits no heating / extruder-mode commands by default**
   `fullcontrol/devices/community/singletool/custom.py:18-27` — temp/fan/`relative_e` steps
   are appended only if the user passes them in `user_overrides`. Selecting the custom
   printer without explicit temps generates gcode that extrudes cold and ignores the
   `relative_e` default from `base_settings`. Emit steps from merged `initialization_data`.

5. **XYZBC inverse kinematics likely wrong for non-zero `bc_intercept`**
   `lab/.../multiaxis/gcode/XYZBC/point.py:46-59` — intercept corrections are layered
   inconsistently onto a full-coordinate rotation matmul, `bc_intercept.y` is explicitly
   dropped (line 53), and `system_point.b/.c` are never re-rounded. Untested against the
   cited LinuxCNC transform. Needs derivation + a unit test.

6. **Unguarded `IndexError` / `ZeroDivisionError` on plausible inputs**
   - `fullcontrol/extra_functions.py:38` — `points_only` `while … new_steps[0]` has no
     empty-list guard.
   - `fullcontrol/extra_functions.py:112` — `linspace(n=1)` divides by `n-1` → ZeroDivision;
     propagates to `arcXY`/`polygonXY`/ramps at `segments=0`.
   - `fullcontrol/visualize/tube_mesh.py:209-212,301` — divides by vector norm with no
     zero guard; coincident successive points → silent `NaN` mesh. `TubeMesh` doesn't
     enforce its own "distinct points" contract (only external `generate_mesh` dedups).

---

## MEDIUM — correctness / robustness

- **`midpoint` crashes on partially-defined points** — `geometry/midpoint.py:16-22`
  (`UnboundLocalError` when a coord is `None`); `interpolated_point` (`:38-43`) uses an
  `or`-guard that still does arithmetic on `None`.
- **`angleXY_between_3_points` returns radians but docstring says degrees**, unnormalized —
  `geometry/measure.py:36-48`.
- **`segmented_path` can index past the last point** under float accumulation —
  `geometry/segmentation.py:48`; also annotated `-> int` but returns a list (`:25`).
- **`reflectXY_mc` divides by zero** for a horizontal mirror line (slope 0) —
  `geometry/reflect.py:17` (public API; `reflectXY` guards but the raw fn doesn't).
- **`squarewaveXY` mutates the caller's `Vector` in place** — `geometry/waves.py:59-62`.
- **First-point / uninitialized-state extrusion hazard** — `gcode/extrusion_classes.py:117`
  `distance_forgiving` silently zeroes missing axes, so a `no_primer` print with no starting
  Point computes a wrong first-move E instead of erroring (only a comment warns, `state.py:58`).
- **`XYZ_gcode` skips any move whose XYZ exactly equals the previous point** —
  `gcode/point.py:20-40` — also skips the `e_gcode` call, desyncing E accounting.
- **Absolute extrusion E grows unbounded** (no periodic `G92 E0`) —
  `gcode/extrusion_classes.py:88` (acknowledged-unimplemented comment).
- **Empty-list `IndexError`** — `gcode/annotations.py:28` `GcodeComment` with
  `end_of_previous_line_text` does `state.gcode[-1] +=` with no guard.
- **`local_max` module-global used as a return channel** — `visualize/plotly.py:26/41/46/89`;
  `if not widths:` never fires for an all-zero width list. Refactor `generate_mesh` to return
  its values.
- **Bounding-box `±1e10` sentinels** yield negative ranges on empty/all-None designs —
  `visualize/bounding_box.py:51-67`.
- **`steps2controlcode` strips Bambu header by hardcoded line indices** —
  `lab/.../controlcode_formats/steps2controlcode.py:85-86`
  (`gcode_str[:15]+gcode_str[16:20]+gcode_str[22:]`); also operates on fixed CWD filenames it
  `rmtree`s (`:17-18,25-26`). Use content-matching + `tempfile`.
- **`rotate` has no guard** for invalid axis string (`UnboundLocalError`) or zero-length axis
  (`ZeroDivisionError`) — `lab/.../geometry/rotate.py:26-33,56-57`.
- **`bezier` refinement** is a fixed-20-iteration heuristic with no convergence/divergence
  guard or tests — `lab/.../geometry/bezier.py:113-130`.
- **`convex` emits a zero-length extrude** (start point emitted as travel then re-extruded) —
  `lab/.../geometry/convex.py:48-54,97-103`.

---

## Cross-cutting patterns (fix once, apply broadly)

- **Pydantic mutable class-level defaults** (`gcode = []`, `point = Point()`,
  `bounding_box = BoundingBox()`) in `gcode/state.py`, `visualize/plot_data.py`,
  `visualize/path.py`. Pydantic v2 deep-copies per instance so it's currently safe, but
  switch to `Field(default_factory=…)` to make the safety explicit and v1-proof.
- **String-based type checks** `type(x).__name__ == 'Point'` (brittle vs subclasses/imports)
  in `geometry/move_polar.py`, `lab/.../state.py` — prefer `isinstance`.
- **`!= None` / `== True`** throughout instead of `is None` / truthiness — masks `None` vs
  falsy bugs (e.g. `extruder.on is None` treated as "travel").
- **Bare `except:`/`try…pass`** swallowing all errors — `gcode/extrusion_classes.py:29-32,129-135`,
  `lab/.../geometry/intersect.py:39`. Catch `TypeError` specifically.
- **Wrong return-type annotations** (`-> float` on functions returning `str`/`None`) —
  `gcode/point.py:8`, all three multiaxis `point.py`.
- **Massive triplication** across `lab/.../multiaxis/gcode/XYZB|XYZBC|XYZC0B1/` (state/printer/
  controls/steps2gcode ~80% identical) and near-identical device profiles
  (`ender_5_plus.py` is a byte-copy of `ender_3.py`; `cr_10`/`prusa_i3` patch steps by magic
  index). Every fix must currently be made N times.
- **`combinations/.../classes.py`** is hand-maintained multiple-inheritance glue the file's
  own comment says should be automated — silent drift risk as subpackages grow.

---

## Quality / maturity notes

- `base.py` validation is leaky: `__setitem__`/`update_from` bypass `reject_extra_fields`
  (construction-only) while `extra="allow"` contradicts the reject-validator.
- `check.stop()` calls `sys.exit()` — kills the Jupyter kernel instead of raising.
- `import_design`/`export_design` use deprecated pydantic-v1 `parse_obj` + fragile `__dict__`
  serialization — won't round-trip nested models reliably on pydantic v2
  (`extra_functions.py:172,192`).
- Library code `print()`s (citation banners) on every call — `lab/.../convex.py:129`,
  `steps2controlcode.py:87`.
- `lab/incubator/performance_test.py` prints **hardcoded "prior" ratios unrelated to the
  actual run** (`:438-466`) and benchmarks µs-scale ops single-shot (measures timer
  overhead). Use `timeit` with inner loops; remove the canned numbers.
- Copy-paste docstrings (`FlowTubeMesh` ≡ `TubeMesh`; `rotate` doc mentions a nonexistent
  `vector` param), placeholder docstrings (`PrinterCommand id (type)`), and stray no-op code
  (`visualize/plotly.py:119` bare `range`).

---

## Suggested priority order

1. `eval()` → whitelist (security).
2. `arcXY_3pt` normalization + the `:.6`→`:.6f` formatting (silent wrong output).
3. `custom` device cold-extrusion default.
4. The unguarded crash paths (`points_only`, `linspace`, `tube_mesh` NaN, `midpoint`).
5. Adopt `default_factory`, `isinstance`, `is None` conventions repo-wide; add a test
   harness — there is currently no visible automated test suite covering these paths.
