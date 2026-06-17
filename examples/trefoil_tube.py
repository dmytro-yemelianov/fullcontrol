"""Trefoil-knot tube - a single-wall tube spiralling along a trefoil knot centre-line.

The trefoil knot centre-line `C(t) = (sin t + 2 sin 2t, cos t - 2 cos 2t, -sin 3t)` is swept into a
tube: at each point the toolpath places a ring perpendicular to the curve tangent (via a Z-up
reference frame that avoids Frenet twist), and the ring angle advances as we march along the knot,
so the whole tube is one continuous helical bead that closes on itself after one traversal.

An art / visualisation piece (a floating knot - needs support to print), but a striking one-bead
non-planar toolpath. See also `mobius_band`.
"""
from math import tau, sin, cos, sqrt

import fullcontrol as fc


def _knot(t: float, scale: float):
    return (scale * (sin(t) + 2 * sin(2 * t)),
            scale * (cos(t) - 2 * cos(2 * t)),
            scale * (-sin(3 * t)))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    m = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _frame(t: float, scale: float):
    'Tangent + a Z-up reference normal/binormal (no Frenet twist) at knot parameter t.'
    tan = _norm(_sub(_knot(t + 1e-4, scale), _knot(t - 1e-4, scale)))
    up = (0.0, 0.0, 1.0) if abs(tan[2]) < 0.95 else (1.0, 0.0, 0.0)
    dot = up[0] * tan[0] + up[1] * tan[1] + up[2] * tan[2]
    nrm = _norm((up[0] - dot * tan[0], up[1] - dot * tan[1], up[2] - dot * tan[2]))
    return nrm, _cross(tan, nrm)


def trefoil_tube(scale: float = 6.0, tube_radius: float = 4.0, tube_turns: int = 120,
                 cross_points: int = 48, extrusion_width: float = 0.6, extrusion_height: float = 0.3,
                 centre=(50.0, 50.0), base_gap: float = 0.8) -> list:
    """Build a trefoil-knot tube toolpath.

    scale: size of the knot (mm per unit); tube_radius: tube wall radius about the centre-line.
    tube_turns: helical wraps around the tube over one knot traversal (more = denser wall);
    cross_points: points per tube cross-section (resolution).
    """
    cx, cy = centre
    z_lift = scale + tube_radius + base_gap         # lift so the lowest point clears the bed
    n = tube_turns * cross_points
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=extrusion_height)]
    for i in range(n + 1):
        s = i / n
        t = s * tau                                  # once around the knot
        phi = s * tau * tube_turns                   # spiral around the tube
        c = _knot(t, scale)
        nrm, bnm = _frame(t, scale)
        cp, sp = cos(phi), sin(phi)
        steps.append(fc.Point(
            x=cx + c[0] + tube_radius * (cp * nrm[0] + sp * bnm[0]),
            y=cy + c[1] + tube_radius * (cp * nrm[1] + sp * bnm[1]),
            z=z_lift + c[2] + tube_radius * (cp * nrm[2] + sp * bnm[2])))
    return steps


if __name__ == '__main__':
    steps = trefoil_tube()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='trefoil_tube',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote trefoil_tube.gcode')
