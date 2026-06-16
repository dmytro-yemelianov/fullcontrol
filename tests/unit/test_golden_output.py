"""Golden-output regression lock.

Captures the full gcode (and plot path coordinates) for a set of representative designs and
asserts they don't change. This encodes, in CI, the byte-identical discipline that refactors
must preserve - so a change that silently alters emitted output fails here even if the
substring/regex characterization tests still pass.

Numeric tokens are normalised to 3 decimal places (1 micron) before comparison, so the lock
is portable across platforms (it ignores last-digit float-formatting noise) while still
catching any structural or meaningful numeric regression.

To regenerate after an *intentional* output change: ``REGEN_GOLDEN=1 pytest tests/unit/test_golden_output.py``
then review the diff.
"""
import os
import re
import pathlib

import fullcontrol as fc

_GOLDEN_DIR = pathlib.Path(__file__).parent / 'golden'
_NUMBER = re.compile(r'-?\d+\.\d+')


def _normalise(text: str) -> str:
    'round every decimal number to 3 dp so the lock ignores sub-micron float-format noise'
    def round3(m):
        return format(round(float(m.group()), 3), '.3f').rstrip('0').rstrip('.')
    return _NUMBER.sub(round3, text)


def _check(name: str, produce) -> None:
    actual = produce()
    path = _GOLDEN_DIR / f'{name}.txt'
    if os.environ.get('REGEN_GOLDEN') or not path.exists():
        _GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(actual)
    expected = path.read_text()
    assert _normalise(actual) == _normalise(expected), (
        f'golden output changed for {name!r}. If intentional, regenerate with '
        f'REGEN_GOLDEN=1 pytest and review the diff.')


def _gcode(steps, printer='generic', **init):
    return lambda: fc.transform(steps, 'gcode',
                                fc.GcodeControls(printer_name=printer, initialization_data={'nozzle_temp': 210, **init}),
                                show_tips=False)


def _plot_paths(steps):
    def produce():
        pd = fc.transform(steps, 'plot', fc.PlotControls(raw_data=True, printer_name='generic'), show_tips=False)
        lines = []
        for i, p in enumerate(pd.paths):
            lines.append(f'path {i}: x={p.xvals} y={p.yvals} z={p.zvals}')
        return '\n'.join(lines)
    return produce


# --- representative designs ---

def _basic():
    return [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.ExtrusionGeometry(width=0.5, height=0.2),
            fc.Point(x=20, y=0, z=0.2), fc.Point(x=20, y=20, z=0.2),
            fc.Retraction(distance=2), fc.Extruder(on=False), fc.Point(x=0, y=20, z=0.2),
            fc.Extruder(on=True), fc.Unretraction(), fc.Point(x=0, y=0, z=0.2)]


def _arcs():
    return [fc.Point(x=20, y=0, z=0.2), fc.Extruder(on=True),
            fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=20), direction='anticlockwise'),
            fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=-20, y=0, z=0.4), direction='clockwise')]


def _aux():
    return [fc.Hotend(temp=215, wait=True), fc.Buildplate(temp=60, wait=False), fc.Fan(speed_percent=80),
            fc.Acceleration(printing=800, travel=1200), fc.Jerk(x=8, y=8), fc.PressureAdvance(value=0.05),
            fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)]


def _klipper():
    return [fc.PressureAdvance(value=0.05), fc.Jerk(x=7, y=7), fc.Hotend(temp=210, wait=True),
            fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)]


def _geometry():
    return fc.circleXY(fc.Point(x=50, y=50, z=0.2), 20, 0, 32) + fc.rectangleXY(fc.Point(x=10, y=10, z=0.4), 30, 20)


def test_golden_basic_gcode():
    _check('basic', _gcode(_basic()))


def test_golden_arcs_gcode():
    _check('arcs', _gcode(_arcs()))


def test_golden_aux_commands_gcode():
    _check('aux', _gcode(_aux()))


def test_golden_klipper_flavor_gcode():
    _check('klipper', _gcode(_klipper(), gcode_flavor='klipper'))


def test_golden_ender3_gcode():
    _check('ender3', _gcode(_basic(), printer='ender_3'))


def test_golden_geometry_gcode():
    _check('geometry', _gcode(_geometry()))


def test_golden_basic_plot():
    _check('basic_plot', _plot_paths(_basic()))
