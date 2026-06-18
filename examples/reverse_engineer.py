"""Reverse-engineer g-code back into the parametric formula that (most likely) generated it.

FullControl goes formula -> steps -> g-code. This goes the other way for the big surface-of-
revolution / vase family (most of the library): parse the g-code to extruding points, decompose them
into cylindrical coordinates about an auto-detected axis, and least-squares-fit the modulation:

  - the base radius profile r0(z)  (constant = cylinder, sloped = cone/taper),
  - the angular harmonics of the radius  (the lobe / wave / ripple count and amplitude), and
  - the angular harmonics of z for non-planar surfaces  (z-undulation count/height).

The dominant harmonic IS the design's `lobes` / `waves` / `star_tips`; its amplitude is the depth.
`reverse_engineer(gcode)` returns a structured report; `describe(report)` renders the recovered
formula. Closed-form for surfaces of revolution; arbitrary 3-D toolpaths are out of scope (that's
symbolic-regression / point-cloud territory). `identify(gcode)` additionally handles the open
corrugated *snake-mode* wall (the Snake-Mode Soapdish), which is not a surface of revolution.
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


def _points(steps):
    return np.array([(p.x, p.y, p.z) for p in steps if getattr(p, 'x', None) is not None])


def _subsample(p, n=500):
    return p if len(p) <= n else p[np.linspace(0, len(p) - 1, n).astype(int)]


def _chamfer(a, b):
    'Symmetric mean nearest-neighbour distance between two point clouds (a fit-quality score, mm).'
    a, b = _subsample(a), _subsample(b)
    d = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    return float(np.sqrt(d.min(1)).mean() + np.sqrt(d.min(0)).mean()) / 2


def _courses_by_z(p):
    'Split a print-ordered point cloud into per-z-level courses (snake mode holds z within a course).'
    zr = np.round(p[:, 2], 3)
    breaks = np.where(np.diff(zr) != 0)[0] + 1
    return [c for c in np.split(np.arange(len(p)), breaks) if len(c) >= 5]


def _snake_wall_params(p):
    '''Recover the open corrugated-wall parameters (the Snake-Mode Soapdish) from its point cloud:
    long-axis length (max course span = mid-height), corrugation count + amplitude (dominant harmonic
    of the across-axis deviation on the widest course), and height. Returns snake_soapdish kwargs.'''
    along_axis = 0 if np.ptp(p[:, 0]) >= np.ptp(p[:, 1]) else 1  # the wall's long axis
    across_axis = 1 - along_axis
    courses = _courses_by_z(p)
    courses.sort(key=lambda c: p[c, 2].mean())
    cmid = courses[len(courses) // 2]              # median-height course (lens peak, primer-proof)

    along, across = p[cmid, along_axis], p[cmid, across_axis]
    length = float(np.ptp(along))
    t = (along - along.min()) / max(np.ptp(along), 1e-9)        # normalised traverse 0..1
    across = across - np.polyval(np.polyfit(t, across, 2), t)   # detrend the gentle bow
    _, harm = _fit_harmonics(2 * np.pi * t, across, min(len(cmid) // 3, 40))
    waves = harm[0][0]                                          # dominant corrugation frequency
    # physical corrugation depth (robust to the harmonic splitting across k and k+1)
    amplitude = float(np.percentile(across, 98) - np.percentile(across, 2)) / 2
    height = float(p[:, 2].max() - p[:, 2].min())

    cx = (p[cmid, along_axis].min() + p[cmid, along_axis].max()) / 2
    cy = (p[cmid, across_axis].min() + p[cmid, across_axis].max()) / 2
    return {'length': round(length, 1), 'height': round(height, 1), 'waves': waves,
            'amplitude': round(float(amplitude), 2),
            'centre': (round(float(cx), 1), round(float(cy), 1))}


def identify(gcode: str) -> dict:
    '''Identify which gallery design (and what parameters) most likely produced the g-code, by
    matching the recovered signature against the gallery's forward models. Returns
    {'design', 'params', 'fit_error'} (fit_error = chamfer distance to the regenerated design, mm).

    Surfaces of revolution (vases) are recovered from cylindrical harmonics: exact lobe/side counts,
    radius, the cosine vase's depth, and the polygon's circumradius (a polygon carries strong energy
    at twice its base harmonic). The Snake-Mode Soapdish is an *open corrugated wall*, not a surface
    of revolution - it is detected because snake mode holds z constant within each course (vases
    spiral z continuously); its corrugation count, length and height are recovered directly.
    '''
    from examples import spiral_vase, twisted_polygon_vase, snake_soapdish
    p = parse_gcode(gcode) if isinstance(gcode, str) else np.asarray(gcode)

    # snake-mode wall vs surface of revolution: snake mode holds z within a course (few z-changes),
    # a vase spirals z continuously (a z-change almost every point). Robust to primer/base contamination.
    z_changes = int((np.diff(np.round(p[:, 2], 3)) != 0).sum())
    if z_changes < 0.2 * len(p):
        design, params = 'snake_soapdish', _snake_wall_params(p)
    else:
        rep = reverse_engineer(gcode)
        (cx, cy), theta, z, r = _cylindrical(p)
        height, count = rep['height'], rep['radial_harmonic']['count']
        # polygon vs sine-lobe: a polygon carries strong energy at 2x/3x the base harmonic
        _, harm = _fit_harmonics(theta, r - np.polyval(np.polyfit(z, r, 1), z),
                                 min(3 * count + 1, len(p) // 4))
        amp = {k: a for k, a, _ in harm}
        if amp.get(2 * count, 0.0) > 0.15 * amp.get(count, 1e9):
            design = 'twisted_polygon_vase'
            params = {'sides': count, 'radius': round(float(r.max()), 1), 'height': round(height, 1),
                      'twist_turns': 0, 'morph_to_sides': 0}
        else:
            design = 'spiral_vase'
            params = {'radius': round(float(rep['base_radius']), 1), 'height': round(height, 1),
                      'lobes': count, 'lobe_depth': round(rep['radial_harmonic']['amplitude'], 2)}

    gen = {'spiral_vase': spiral_vase, 'twisted_polygon_vase': twisted_polygon_vase,
           'snake_soapdish': snake_soapdish}[design]
    fit_error = round(_chamfer(p, _points(gen(**params))), 3)
    return {'design': design, 'params': params, 'fit_error': fit_error}


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
