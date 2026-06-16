"""The geometry generators are backend-free: they build designs from core data classes and
depend only on fullcontrol.core (enforced by test_core_boundary). color is a plain data field
on the core Point, so geometry results are still colourable and fully renderable.
"""
import ast
import pathlib

import fullcontrol as fc
import fullcontrol.geometry


def test_geometry_returns_core_points():
    pts = fc.circleXY(fc.Point(x=0, y=0, z=0), 10, 0, 8)
    assert type(pts[0]).__module__ == 'fullcontrol.core.point'


def test_core_point_has_a_color_data_field():
    p = fc.Point(x=0, y=0, z=0)
    p.color = [1, 0, 0]            # must not raise - color is a core data attribute
    assert p.color == [1, 0, 0]
    assert fc.Point(x=0, y=0, z=0, color=[0, 1, 0]).color == [0, 1, 0]


def test_geometry_points_are_colourable():
    pts = fc.circleXY(fc.Point(x=0, y=0, z=0), 10, 0, 8)
    pts[0].color = [1, 0, 0]
    assert pts[0].color == [1, 0, 0]


def test_geometry_design_renders():
    g = fc.transform(fc.circleXY(fc.Point(x=50, y=50, z=0.2), 10, 0, 16),
                     'gcode', fc.GcodeControls(printer_name='generic',
                                               initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert g.count('G1') >= 16  # one move per circle segment


def test_geometry_package_is_backend_free():
    backends = ('fullcontrol.gcode', 'fullcontrol.visualize', 'fullcontrol.combinations')
    geom_dir = pathlib.Path(fullcontrol.geometry.__file__).parent
    offenders = []
    for py in geom_dir.glob('*.py'):
        for node in ast.walk(ast.parse(py.read_text())):
            mod = node.module if isinstance(node, ast.ImportFrom) and node.module else None
            if mod and any(mod == b or mod.startswith(b + '.') for b in backends):
                offenders.append(f'{py.name} imports {mod}')
    assert not offenders, f'geometry must be backend-free: {offenders}'
