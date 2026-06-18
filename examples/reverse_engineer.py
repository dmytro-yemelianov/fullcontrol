"""Reverse-engineer g-code back into the parametric formula that (most likely) generated it.

FullControl goes formula -> steps -> g-code. This goes the other way for the big surface-of-
revolution / vase family (most of the library): parse the g-code to extruding points, decompose them
into cylindrical coordinates about an auto-detected axis, and least-squares-fit the modulation:

  - the base radius profile r0(z)  (constant = cylinder, sloped = cone/taper),
  - the angular harmonics of the radius  (the lobe / wave / ripple count and amplitude), and
  - the angular harmonics of z when the print snakes up and down  (snake-mode spike count/height).

The dominant harmonic IS the design's `lobes` / `waves` / `star_tips`; its amplitude is the depth.
`reverse_engineer(gcode)` returns a structured report; `describe(report)` renders the recovered
formula. Closed-form for surfaces of revolution; arbitrary 3-D toolpaths are out of scope (that's
symbolic-regression / point-cloud territory).
"""
import numpy as np


def parse_gcode(text: str):
    'Parse g-code into an (N, 3) array of *extruding* move endpoints (E increases, XY moves).'
    pts = []
    x = y = z = e = 0.0
    relative_e = False
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('M83'):
            relative_e = True
        elif s.startswith('M82'):
            relative_e = False
        elif s[:3] in ('G1 ', 'G0 '):
            d = {}
            for tok in s.split()[1:]:
                if tok and tok[0] in 'XYZEF':
                    try:
                        d[tok[0]] = float(tok[1:])
                    except ValueError:
                        pass
            nx, ny, nz = d.get('X', x), d.get('Y', y), d.get('Z', z)
            de = d.get('E', 0.0) if relative_e else d.get('E', e) - e
            if de > 1e-9 and (nx != x or ny != y or nz != z):
                pts.append((nx, ny, nz))
            x, y, z = nx, ny, nz
            if 'E' in d:
                e = e if relative_e else d['E']
    return np.array(pts) if pts else np.empty((0, 3))


def _cylindrical(p):
    cx, cy = p[:, 0].mean(), p[:, 1].mean()
    theta = np.arctan2(p[:, 1] - cy, p[:, 0] - cx)
    r = np.hypot(p[:, 0] - cx, p[:, 1] - cy)
    return (cx, cy), theta, p[:, 2], r


def _fit_harmonics(angles, values, k_max):
    '''Least-squares fit values ~ a0 + sum_k ak cos(k.angle) + bk sin(k.angle) (robust to non-uniform
    sampling). Returns (dc, harmonics) where harmonics is [(k, amplitude, phase)] sorted by amplitude.'''
    cols = [np.ones_like(angles)]
    for k in range(1, k_max + 1):
        cols += [np.cos(k * angles), np.sin(k * angles)]
    coef, *_ = np.linalg.lstsq(np.column_stack(cols), values, rcond=None)
    harmonics = []
    for k in range(1, k_max + 1):
        a, b = coef[2 * k - 1], coef[2 * k]
        harmonics.append((k, float(np.hypot(a, b)), float(np.arctan2(b, a))))
    harmonics.sort(key=lambda h: -h[1])
    return float(coef[0]), harmonics


def reverse_engineer(gcode: str, max_harmonic: int = 60) -> dict:
    'Recover the surface-of-revolution parameters/formula behind a g-code file. See module docstring.'
    p = parse_gcode(gcode) if isinstance(gcode, str) else np.asarray(gcode)
    if len(p) < 16:
        raise ValueError('not enough extruding points to analyse')
    (cx, cy), theta, z, r = _cylindrical(p)
    z0, z1 = float(z.min()), float(z.max())
    height = z1 - z0

    # base radius profile r0(z) = a + b*z  (cylinder vs cone/taper)
    b, a = np.polyfit(z, r, 1) if height > 1e-6 else (0.0, float(r.mean()))
    base_radius, top_radius = a + b * z0, a + b * z1
    radial_change = abs(top_radius - base_radius)
    profile = 'cylinder' if radial_change < 0.5 else ('cone/taper' if b < 0 else 'flared')

    # angular harmonics of the radius residual (lobes / waves / ripples)
    r_dc, r_harm = _fit_harmonics(theta, r - (a + b * z), min(max_harmonic, len(p) // 4))
    # angular harmonics of z, detrended by a smooth rising baseline (snake-mode spikes)
    zb, za = np.polyfit(theta * 0 + np.arange(len(z)) / len(z), z, 1)  # rise vs print progress
    _, z_harm = _fit_harmonics(theta, z - (za + zb * np.arange(len(z)) / len(z)),
                               min(max_harmonic, len(p) // 4))

    radial = r_harm[0]
    vertical = z_harm[0]
    return {
        'n_points': int(len(p)),
        'centre': (round(cx, 2), round(cy, 2)),
        'height': round(height, 2),
        'base_radius': round(base_radius, 2),
        'top_radius': round(top_radius, 2),
        'profile': profile,
        'radial_harmonic': {'count': radial[0], 'amplitude': round(radial[1], 3)},
        'vertical_harmonic': {'count': vertical[0], 'amplitude': round(vertical[1], 3)},
        'modulation': 'radial' if radial[1] >= vertical[1] else 'vertical',
    }


def describe(report: dict) -> str:
    'Render the recovered formula and parameters as human-readable text.'
    c = report['centre']
    lines = [f"~{report['n_points']} points about axis ({c[0]}, {c[1]}); height {report['height']} mm",
             f"radius profile: {report['profile']}  ({report['base_radius']} -> {report['top_radius']} mm)"]
    if report['modulation'] == 'radial':
        h = report['radial_harmonic']
        lines.append(f"radial modulation: {h['count']} lobes/waves, depth {h['amplitude']} mm")
        lines.append(f"  => r(theta, z) ~= {report['base_radius']:.1f}..{report['top_radius']:.1f} "
                     f"+ {h['amplitude']:.2f}*cos({h['count']}*theta)")
    else:
        h = report['vertical_harmonic']
        lines.append(f"snake-mode vertical modulation: {h['count']} spikes, height ~{h['amplitude']:.2f} mm")
        lines.append(f"  => z(theta) ~= base(z) + ~{h['amplitude']:.2f}*spike({h['count']}*theta)")
    return '\n'.join(lines)


if __name__ == '__main__':
    import fullcontrol as fc
    from examples import spiral_vase
    gc = fc.transform(spiral_vase(radius=15, lobes=5, lobe_depth=2), 'gcode',
                      fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                      show_tips=False)
    print(describe(reverse_engineer(gc)))
