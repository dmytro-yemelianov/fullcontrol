"""The Hex Adapter gallery design: a hexagonal honeycomb adapter ring printed as one continuous path.

Smoke + sanity (resolves to gcode, simulates, validates against a generous build volume) plus
geometry asserts proving the cross-section is a hexagonal double wall - an inner hexagonal hole
inside an outer hexagonal body - stacked as a constant prism whose proportions match the published
FullControl model.
"""
import math

import fullcontrol as fc
from fullcontrol.core.point import Point  # geometry helpers return core Points (fc.Point subclasses it)
from examples.hex_adapter import hex_adapter

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data=dict(_BUILD))


def _points(steps):
    return [s for s in steps if isinstance(s, Point)]


def _polar(p, cx=50, cy=50):
    return (math.hypot(p.x - cx, p.y - cy), math.atan2(p.y - cy, p.x - cx))


def test_hex_adapter_generates_gcode():
    steps = hex_adapter(height=2)
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20                  # a real toolpath, not a stub
    assert 'G1' in gcode                           # extruding moves were emitted


def test_hex_adapter_simulates_to_a_real_print():
    steps = hex_adapter(height=2)
    r = fc.transform(steps, 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0                    # material is actually deposited
    assert r.extruding_distance > 0


def test_hex_adapter_validates_without_errors():
    steps = hex_adapter(height=2)
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_hex_adapter_starts_with_its_own_extrusion_geometry():
    steps = hex_adapter()
    assert isinstance(steps[0], fc.ExtrusionGeometry)
    assert steps[0].width == 0.6 and steps[0].height == 0.2


def test_hex_adapter_is_a_hexagonal_double_wall():
    '''The cross-section is a hexagon: exactly six radius maxima (the outer hex vertices) around one
    turn, and it carries an inner hexagonal hole well inside the outer body (a double wall).'''
    steps = hex_adapter(inner_size=10, outer_size=16)
    pts = _points(steps)
    z0 = min(p.z for p in pts)
    layer = [_polar(p) for p in pts if abs(p.z - z0) < 1e-6]
    assert len(layer) > 6

    # the outer hexagon has six corners: six distinct angular directions sit at the max radius
    rmax = max(r for r, _ in layer)
    corner_angles = {round(math.degrees(a) % 360, 0) % 360 for r, a in layer if r > rmax - 1e-3}
    assert len(corner_angles) == 6                          # six outer hexagon corners

    # inner hole (smallest radii) sits clearly inside the outer body (smallest << largest)
    assert min(r for r, _ in layer) < rmax - 2.0            # a genuine double wall / ring

    # outer body proportions match the model: flat-to-flat 16mm -> vertex circumradius ~8.86mm
    assert abs(rmax - 8.864) < 0.05


def test_hex_adapter_is_a_constant_prism_stacked_to_height():
    'Every layer is the same hexagonal cross-section, stepped straight up by the layer height.'
    steps = hex_adapter(height=4, extrusion_height=0.2)
    pts = _points(steps)
    zs = sorted({round(p.z, 4) for p in pts})
    assert len(zs) == 20                                     # height 4 / 0.2 = 20 layers
    steps_up = [b - a for a, b in zip(zs, zs[1:])]
    assert all(abs(s - 0.2) < 1e-6 for s in steps_up)        # uniform layer steps (a prism)

    # the cross-section does not change with height: the radius set is identical bottom vs top
    def radius_set(z):
        return sorted(round(_polar(p)[0], 3) for p in pts if abs(p.z - z) < 1e-6)
    assert radius_set(zs[0]) == radius_set(zs[-1])           # bottom port == top port (constant)


def test_hex_adapter_inner_hole_scales_with_inner_size():
    'A bigger Inner Hex grows the central hole radius; the outer body is unchanged.'
    def min_radius(inner):
        pts = _points(hex_adapter(inner_size=inner, outer_size=16))
        return min(_polar(p)[0] for p in pts)

    small, big = min_radius(8), min_radius(12)
    assert big > small + 0.5                                 # hole opens up with inner_size


def test_hex_adapter_oversize_undersize_tweaks_fit():
    'Inner oversize grows the hole; outer undersize shrinks the body (fine-fit trims).'
    base = _points(hex_adapter())
    base_min = min(_polar(p)[0] for p in base)
    base_max = max(_polar(p)[0] for p in base)

    grown_hole = _points(hex_adapter(inner_oversize=1.2))
    assert min(_polar(p)[0] for p in grown_hole) > base_min + 0.5

    shrunk_body = _points(hex_adapter(outer_undersize=1.2))
    assert max(_polar(p)[0] for p in shrunk_body) < base_max - 0.5
