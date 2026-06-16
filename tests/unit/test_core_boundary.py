"""fullcontrol.core is the backend-free foundation: data model + utilities.

It must not depend on the gcode/visualize backends - that is the core/backend boundary,
enforced here statically so it can't silently erode.
"""
import ast
import pathlib

import fullcontrol.core

_CORE_DIR = pathlib.Path(fullcontrol.core.__file__).parent
_BACKENDS = ('fullcontrol.gcode', 'fullcontrol.visualize', 'fullcontrol.combinations')


def _module_imports(path):
    names = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
    return names


def test_core_modules_do_not_import_backends():
    offenders = []
    for py in _CORE_DIR.glob('*.py'):
        for imp in _module_imports(py):
            if any(imp == b or imp.startswith(b + '.') for b in _BACKENDS):
                offenders.append(f'{py.name} imports {imp}')
    assert not offenders, f'core must be backend-free: {offenders}'


def test_core_exposes_the_data_model():
    import fullcontrol.core as core
    for name in ('BaseModelPlus', 'Point', 'Printer', 'Extruder', 'ExtrusionGeometry',
                 'Fan', 'Hotend', 'Buildplate', 'check', 'fix', 'linspace'):
        assert hasattr(core, name), name


def test_legacy_import_paths_still_work():
    # the old fullcontrol.<module> paths re-export from core, so nothing breaks
    from fullcontrol.base import BaseModelPlus  # noqa: F401
    from fullcontrol.point import Point
    from fullcontrol.common import Extruder, linspace  # noqa: F401
    assert Point.__module__ == 'fullcontrol.core.point'
