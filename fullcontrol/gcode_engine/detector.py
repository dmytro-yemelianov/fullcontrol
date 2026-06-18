"""ParseParams - the dialect/flavor context the g-code parser needs.

The parser must know a few things that g-code itself does not always state explicitly: the
firmware flavor (for re-emitting flavor-specific commands), whether E is relative or absolute,
whether E is in mm of filament or mm^3 (volumetric), and the feedstock diameter (to convert E
back to a deposited volume). `ParseParams` carries these.

Two constructors:

* `ParseParams.detect(text)` sniffs them from the g-code itself - M82/M83 for absolute/relative
  E, slicer header comments and Klipper-specific commands for the flavor, `;FLAVOR:`/diameter/
  volumetric comments where slicers write them.
* `ParseParams.from_controls(controls)` reconstructs the *exact* params a `GcodeControls`
  produced, so the round-trip test can parse our own output with the same context the emitter
  used. This mirrors `fullcontrol.gcode.state.State.__init__`.
"""
from dataclasses import dataclass


@dataclass
class ParseParams:
    '''Parsing context for `parse_gcode`.

    Attributes:
        flavor: firmware dialect ('marlin' | 'klipper' | 'duet' | 'reprapfirmware').
        relative_e: True for M83 relative extrusion, False for M82 absolute.
        e_units: 'mm' (filament length) or 'mm3' (volumetric E).
        dia_feed: feedstock filament diameter (mm); converts E<->volume in 'mm' mode.
        travel_g1_e0: True when travel moves are emitted as 'G1 ... E0' (travel_format G1_E0).
    '''
    flavor: str = 'marlin'
    relative_e: bool = True
    e_units: str = 'mm'        # 'mm' | 'mm3'
    dia_feed: float = 1.75
    travel_g1_e0: bool = False

    # ---- detection from raw g-code ----------------------------------------------------

    @classmethod
    def detect(cls, text: str) -> 'ParseParams':
        '''Sniff parsing params from g-code text (best-effort; never raises).

        Reads M82/M83 for the E mode, scans header comments and command vocabulary for the
        flavor, and `;FILAMENT`/`;FLAVOR`/volumetric markers some slicers write.
        '''
        p = cls()
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            upper = line.upper()
            code = upper.split(';', 1)[0].strip()  # the command part (comments stripped)

            # E mode (M82 absolute / M83 relative) - first occurrence wins
            if code.startswith('M83'):
                p.relative_e = True
            elif code.startswith('M82'):
                p.relative_e = False

            # G1_E0 travel format: a travel-shaped G1 (X/Y move) carrying exactly E0
            if code.startswith('G1') and 'E0' in code.replace(' ', '') and ('X' in code or 'Y' in code):
                toks = code.split()
                for t in toks:
                    if t.startswith('E') and t[1:] in ('0', '0.0', '0.000000'):
                        p.travel_g1_e0 = True

            # Klipper-specific commands -> klipper flavor
            if code.startswith('SET_PRESSURE_ADVANCE') or code.startswith('SET_VELOCITY_LIMIT'):
                p.flavor = 'klipper'
            # Duet / RepRapFirmware specific commands
            elif code.startswith('M566') or code.startswith('M572'):
                p.flavor = 'duet'

            # slicer header comments
            if line.startswith(';'):
                low = line.lower()
                if 'flavor:' in low:
                    val = low.split('flavor:', 1)[1].strip()
                    if 'klipper' in val:
                        p.flavor = 'klipper'
                    elif 'reprap' in val or 'duet' in val:
                        p.flavor = 'duet'
                    elif 'marlin' in val:
                        p.flavor = 'marlin'
                if 'klipper' in low and 'flavor' not in low:
                    p.flavor = 'klipper'
                # volumetric extrusion markers
                if 'use_volumetric' in low and 'true' in low:
                    p.e_units = 'mm3'
                if 'volumetric_extrusion' in low and ('1' in low or 'true' in low):
                    p.e_units = 'mm3'
                # filament diameter
                if 'filament_diameter' in low or 'filament diameter' in low:
                    p.dia_feed = _extract_number(low) or p.dia_feed
        return p

    # ---- reconstruction from a GcodeControls ------------------------------------------

    @classmethod
    def from_controls(cls, controls) -> 'ParseParams':
        '''Reconstruct the exact params a GcodeControls produces (mirrors State.__init__).

        Resolves the printer's initialization_data the same way the gcode State does, so the
        round-trip test parses our own output with the identical flavor / E-mode / units / dia.
        '''
        from fullcontrol.gcode.import_printer import resolve_initialization_data
        controls.initialize()
        data = resolve_initialization_data(controls.printer_name, controls.initialization_data)
        return cls(
            flavor=data.get('gcode_flavor', 'marlin'),
            relative_e=bool(data['relative_e']),
            e_units=data['e_units'],
            dia_feed=data['dia_feed'],
            travel_g1_e0=(data['travel_format'] == 'G1_E0'),
        )


def _extract_number(s: str):
    'Pull the first float out of a comment line (best-effort).'
    import re
    m = re.search(r'(\d+\.?\d*)', s)
    return float(m.group(1)) if m else None
