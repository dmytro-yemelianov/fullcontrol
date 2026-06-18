# FullControl Design Library — Catalogue

Source: https://fullcontrol.xyz (SPA). Each model page lives at `#/models/<hash>`.
Captured: 2026-06-18. Total models live: **16** (plus 12 "Coming soon" empty slots).

Notes on capture method:
- Parameters were read from the DOM (sliders are native `<input type=number>` with min/max/step/value; plus checkboxes and one custom combobox).
- Every model exposes a standard **Printer Parameters** block (identical across all models): Nozzle temperature °C (50–600, def 210), Bed temperature °C (0–200, def 50), Fan speed % (0–100, def 100), Material flow % (1–1000, def 100), Print speed % (1–1000, def 100). To avoid repetition this block is listed once below and referenced as "Standard Printer Params" per model.
- Descriptions come from the library card text. Sliders also have a "Regenerate Design" button and a 3D viewer with annotations.
- A few models have list-based / advanced inputs (radii, angles, type selectors) rendered as custom widgets that did not all expose native values; these are noted per-model.

## Standard Printer Params (common to all 16 models)
| name | type | range | default |
|---|---|---|---|
| Nozzle temperature (°C) | slider | 50–600, step 1 | 210 |
| Bed temperature (°C) | slider | 0–200, step 1 | 50 |
| Fan speed (%) | slider | 0–100, step 1 | 100 |
| Material flow (%) | slider | 1–1000, step 1 | 100 |
| Print speed (%) | slider | 1–1000, step 1 | 100 |

---

## 1. Nonplanar Spacer
- Hash: `971ff7`
- Description: "Demo of nonplanar printing for a function spacer component. E.g. used on a bolt or screwed onto something."
- Printing notes (viewer annotations): "Initial approach set under a wave-crest to avoid defects"; "A pointy nozzle is best"; "Spiral flow stabiliser"; Start/End markers. Nonplanar (wavy Z) toolpath.

| name | type | range | default |
|---|---|---|---|
| Waves | slider | 1–10, step 1 | 6 |
| Thickness (mm) | slider | 0–10, step 1 | 4 |
| Hole size (mm) | slider | 4–10, step 1 | 8 |
| Diameter ratio | slider | 1.5–5, step 0.5 | 3 |
| Material thickness (mm) | slider | 0.2–2, step 0.1 | 0.4 |
| Extrudate aspect ratio | slider | 1–4, step 1 | 2 |
| Extrudate overlap % | slider | 0–40, step 1 | 20 |
| Wave contraction factor | slider | 0–2 | 1.2 |
| Quantity | slider | 1–5, step 1 | 1 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/nonplanar-spacer.gcode

---

## 2. Hex Adapter
- Hash: `ff1d4e`
- Description: "Demo of creating a lattice hex adaptor with a continuous print path."
- Printing notes: continuous-path lattice; supports multipart layout (Quantity + offsets).

| name | type | range | default |
|---|---|---|---|
| Inner Hex Oversize (mm) | slider | -2–2, step 1 | 0.2 |
| Outer Hex Undersize (mm) | slider | -2–2, step 1 | 0.2 |
| Extrusion Width (mm) | slider | 0.3–2, step 0.1 | 0.6 |
| Extrusion Height (mm) | slider | 0.1–1, step 0.1 | 0.2 |
| Quantity | slider | 1–5, step 1 | 1 |
| Multipart Offset X (mm) | slider | -100–100, step 1 | 0 |
| Multipart Offset Y (mm) | slider | -100–100, step 1 | 40 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/hex-adapter.gcode

---

## 3. Fractional Design Engine (Polar)
- Hash: `a72616`
- Description: "Define lists of radii and polar angles to create custom lattices."
- Printing notes: Has additional list-based advanced inputs (lists of radii / polar angles) rendered as custom/text widgets not fully enumerated here. Retraction optional (checkbox).

| name | type | range | default |
|---|---|---|---|
| X centre | slider | -1e6–1e6 | 50 |
| Y centre | slider | -1e6–1e6 | 50 |
| Extrusion Width (mm) | slider | 0–1e6 | 0.6 |
| Extrusion Height (mm) | slider | 0–1e6 | 0.2 |
| Use Retraction? | checkbox | on/off | off |
| (radii list / polar-angle list) | text/list | — | model-defined |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/fractional-design-engine-polar.gcode

---

## 4. Ripple Texture Demo
- Hash: `4a0397`
- Description: "Demo of ripple texture achieved by printing offset wavey lines."

| name | type | range | default |
|---|---|---|---|
| Nozzle Diameter (mm) | slider | 0.3–1.2, step 0.1 | 0.4 |
| Ripples Per Layer | slider | 20–100, step 1 | 50 |
| Ripple Depth (mm) | slider | 0–5, step 0.25 | 1 |
| Start Tip Pointiness | slider | 0.25–5, step 0.25 | 1.5 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/ripple-texture.gcode

---

## 5. Tape-Reinforcement Research Demo
- Hash: `eac87f`
- Description: "Physio tape was reinforced with TPU lattices - read the article: tinyurl.com/3Dtape. This design allows a tape-placement guide and/or tape reinforcement to be printed together or separately."
- Printing notes: TPU lattice on tape; research demo.

| name | type | range | default |
|---|---|---|---|
| Tape Width (mm) | slider | 5–100, step 1 | 40 |
| Tape Length (mm) | slider | 5–300, step 1 | 150 |
| Wave Amplitude (%) | slider | 0–200, step 1 | 99 |
| Tape Thickness (mm) | slider | 0–2 | 0.6 |
| Extrusion Width (mm) | slider | 0.2–4 | 0.5 |
| Extrusion Height (mm) | slider | 0.1–2 | 0.2 |
| Layers | slider | 1–5, step 1 | 2 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/tape-reinforcement.gcode

---

## 6. Overhang Challenge
- Hash: `b70938`
- Description: "Try to print an overhang of 90 degrees."
- Printing notes: 90° overhang test; "Five-Stack (Heatsink Demo)" mode via checkbox.

| name | type | range | default |
|---|---|---|---|
| Scale Factor XY | slider | 0.5–3, step 0.5 | 1 |
| Scale Factor Z | slider | 0.5–3, step 0.5 | 1 |
| Five-Stack (Heatsink Demo) | checkbox | on/off | off |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/overhang-challenge.gcode

---

## 7. Overhang Challenge Plus
- Hash: `2d37a5`
- Description: "Try to print an overhang of 90 degrees with different shapes and either inwards or outwards from the supporting wall."
- Printing notes: As Overhang Challenge but with shape/direction options (likely in custom advanced widgets not all enumerated). "Five-Stack (Heatsink Demo)" checkbox.

| name | type | range | default |
|---|---|---|---|
| Scale Factor XY | slider | 0.5–3, step 0.5 | 1 |
| Scale Factor Z | slider | 0.5–3, step 0.5 | 1 |
| Five-Stack (Heatsink Demo) | checkbox | on/off | off |
| (shape / inwards-outwards options) | custom | — | model-defined |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/overhang-challenge-plus.gcode

---

## 8. 2000-Retractions Test (<1 hour)
- Hash: `3bfcdb`
- Description: "Test lots of retraction settings under lots of printing conditions."
- Printing notes: retraction stress test; three checkboxes shorten the test.

| name | type | range | default |
|---|---|---|---|
| Layers | slider | 1–5, step 1 | 1 |
| Z Offset (mm) | slider | -10–10, step 1 | 0 |
| Fewer Sets | checkbox | on/off | off |
| Fewer Travel Lines | checkbox | on/off | off |
| Fewer Lines per Set | checkbox | on/off | off |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/2000-retractions-test.gcode

---

## 9. Star-Polygon Lattice Research
- Hash: `1d3528`
- Description: "Mathematical lattices studied in a research paper - full details at www.tinyurl.com/lattice-research."
- Printing notes: Star/polygon lattice params (count, points) likely in custom advanced widgets; basic geometry captured below.

| name | type | range | default |
|---|---|---|---|
| Extrusion Width (mm) | slider | 0–100 | 0.5 |
| Extrusion Height (mm) | slider | 0.01–5 | 0.2 |
| Layers | slider | 1–5, step 1 | 2 |
| X Start (mm) | slider | -1e6–1e6 | 30 |
| Y Start (mm) | slider | -1e6–1e6 | 30 |
| (star-polygon shape params) | custom | — | model-defined |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/star-polygon-lattice.gcode

---

## 10. FullControl AnyAngle Phone Stand
- Hash: `4d0e78`
- Description: "Lattice phone stand to hold a phone in portrait and landscape modes."

| name | type | range | default |
|---|---|---|---|
| Stand Height (mm) | slider | 20–40, step 1 | 30 |
| Stand Angles (mm) | slider | 9–19, step 2 | 13 |
| Clamping Tightness (%) | slider | 0–100, step 10 | 50 |
| Wave Size (%) | slider | 50–150, step 10 | 100 |
| Angry Mode | checkbox | on/off | off |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/anyangle-phone-stand.gcode

---

## 11. Pin-Support Challenge
- Hash: `67cf20`
- Description: "Print continuously in the Z direction to make a vertical pin. Then print a sphere or cone on top."
- Printing notes: continuous-Z pin then sphere/cone; "Conical Start" checkbox; separate speed controls for sphere/cone vs pillar.

| name | type | range | default |
|---|---|---|---|
| Pillar Diameter (mm) | slider | 0.4–10 | 1.2 |
| Top Purge (mm3) | slider | -10–10 | 0 |
| Bottom Purge (mm3) | slider | -10–10 | 0.5 |
| Sphere/Cone Speed Min (mm/min) | slider | 10–100 | 40 |
| Sphere/Cone Speed Max (mm/min) | slider | 100–5000 | 500 |
| Pillar Speed (mm/min) | slider | 1–100 | 10 |
| Nozzle Size (mm) | slider | 0.2–5 | 0.4 |
| Conical Start | checkbox | on/off | off |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/pin-support-challenge.gcode

---

## 12. Snake-Mode Soapdish
- Hash: `7d3dc2`
- Description: "Snake-mode printing demo - like vase mode but for open structures. Print one way, move up, print the other way, move up, repeat! It's a really nice way to simplify toolpath design."
- Printing notes: SNAKE MODE (continuous Z-rise, open structure; vase-mode-like). No design sliders exposed — fixed geometry demo; only the Standard Printer Params are adjustable.

| name | type | range | default |
|---|---|---|---|
| (no design parameters) | — | — | — |
| Standard Printer Params only | | | |

- gcode: /tmp/fcxyz/snake-mode-soapdish.gcode

---

## 13. FullControl Lampshade
- Hash: `ebdc86`
- Description: "Mathematically defined parametric lampshade."

| name | type | range | default |
|---|---|---|---|
| Internal Hole Radius (mm) | slider | 0–20, step 0.5 | 15 |
| Inner-Frame Amplitude (mm) | slider | 0–100, step 1 | 17.5 |
| Centre XY (mm) | slider | -1000–1000, step 1 | 105 |
| + Standard Printer Params | | | |

- gcode: download failed (params captured; gcode click issued but file did not finalize before navigation)

---

## 14. Blob Printing
- Hash: `800020`
- Description: "Print with blobs instead of lines."

| name | type | range | default |
|---|---|---|---|
| Blob Width (mm) | slider | 0.6–2 | 1.6 |
| Blob Overlap (%) | slider | 0–50, step 1 | 33 |
| Extrusion Speed (mm/min or mm3/min) | slider | 1–10000, step 1 | 100 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/blob-printing.gcode

---

## 15. Nuts and Bolts
- Hash: `393a4c`
- Description: "Parametrically adjust models for nuts, bolts, and internally/externally threaded tubes."
- Printing notes: Has a custom **Type combobox** (default "Generic"; selects nut/bolt/threaded-tube variant). Supports multipart layout.

| name | type | range | default |
|---|---|---|---|
| Type | combobox (custom) | Generic, ... (thread variants) | Generic |
| Clearance (mm) | slider | -10–10 | 0.1 |
| Extrusion Width (mm) | slider | 0.3–2, step 0.1 | 0.6 |
| Extrusion Height (mm) | slider | 0.1–1, step 0.05 | 0.15 |
| Quantity | slider | 1–4, step 1 | 1 |
| Multipart Offset X (mm) | slider | -100–100, step 1 | 0 |
| Multipart Offset Y (mm) | slider | -100–100, step 1 | 40 |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/nuts-and-bolts.gcode

---

## 16. Freeform Frosting Challenge
- Hash: `c5042e`
- Description: "Create freeform helical structures with a frosty texture."
- Printing notes: Helical/freeform; supports fan-speed and print-speed variation along the print (two checkboxes). Two of the four design sliders only exposed a generic "Design Parameters" label (likely Height/Helix-related); ranges captured.

| name | type | range | default |
|---|---|---|---|
| Diameter at top (mm) | slider | 0–60, step 0.5 | 0 |
| Concave offset (mm) | slider | -20–20, step 0.5 | 0 |
| (design param, unnamed #1) | slider | 0–100, step 5 | 50 |
| (design param, unnamed #2) | slider | 10–50, step 5 | 30 |
| Enable fan speed variation | checkbox | on/off | off |
| Enable print speed variation | checkbox | on/off | off |
| + Standard Printer Params | | | |

- gcode: /tmp/fcxyz/freeform-frosting.gcode
