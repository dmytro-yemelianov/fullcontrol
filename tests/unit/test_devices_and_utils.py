"""Characterization tests for FullControl DEVICE profiles and utility functions.

These tests pin the current, observed behaviour of the public API so that future
refactors are safe. They use only the documented public surface:

    import fullcontrol as fc
    fc.transform(steps, 'gcode', fc.GcodeControls(...), show_tips=False)

plus the two import_printer helpers that the repo already treats as testable
(``safe_eval`` is security-critical and exercised directly).

Areas covered:
  * every singletool printer profile -> simple design transforms to gcode with 'G1'
  * a Cura printer with template substitution -> no leftover '{', emits a heat command
  * safe_eval -> evaluates allowed grammar, rejects arbitrary code (ValueError)
  * extra_functions: points_only, relative_point, flatten, first_point/last_point,
    linspace, travel_to
  * export_design / import_design round-trip (pydantic v2 model_validate)
  * a 'custom' printer still emits an extruder-mode line (M82/M83)
"""
import os
import re

import pytest

import fullcontrol as fc
from fullcontrol.gcode.import_printer import safe_eval


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_SINGLETOOL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'fullcontrol', 'devices', 'community', 'singletool',
)
_EXCLUDED_PROFILES = {'__init__', 'base_settings', 'custom', '_procedure'}


def _singletool_profiles():
    """Profile module names to sweep (the real, end-user printers)."""
    names = []
    for fname in os.listdir(_SINGLETOOL_DIR):
        if not fname.endswith('.py'):
            continue
        stem = fname[:-3]
        if stem in _EXCLUDED_PROFILES:
            continue
        names.append(stem)
    return sorted(names)


def _simple_design():
    """A minimal three-point extruding path on a single layer."""
    return [
        fc.Point(x=0, y=0, z=0.2),
        fc.Point(x=10, y=0, z=0.2),
        fc.Point(x=10, y=10, z=0.2),
    ]


_INIT_DATA = {'nozzle_temp': 210, 'bed_temp': 60}
_HEAT_RE = re.compile(r'\bM1(?:04|09|40|90)\b')  # set/wait hotend or bed temperature


# --------------------------------------------------------------------------- #
# 1. per-printer sweep: every singletool profile produces extruding gcode
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('printer_name', _singletool_profiles())
def test_singletool_profile_emits_g1(printer_name):
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name=printer_name, initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert isinstance(gcode, str)
    assert 'G1' in gcode, f'{printer_name} produced no G1 extrusion move'


def test_singletool_sweep_is_non_empty():
    # guard against the parametrization silently collecting zero profiles
    profiles = _singletool_profiles()
    assert len(profiles) >= 10
    assert 'generic' in profiles
    assert 'custom' not in profiles  # excluded -> covered by dedicated tests


@pytest.mark.parametrize('printer_name', _singletool_profiles())
def test_singletool_profile_sets_extruder_mode(printer_name):
    # every singletool profile sets the extruder relative/absolute mode
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name=printer_name, initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert ('M82' in gcode) or ('M83' in gcode), f'{printer_name} set no extruder mode'


# --------------------------------------------------------------------------- #
# 2. Cura printer: template substitution + heat command
# --------------------------------------------------------------------------- #

_CURA_PRINTER = 'Cura/Modix V3 BIG-120X'


def test_cura_printer_transforms_to_g1():
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name=_CURA_PRINTER, initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert 'G1' in gcode


def test_cura_printer_substitutes_all_template_variables():
    # after substitution there must be no leftover '{' template markers anywhere
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name=_CURA_PRINTER, initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert '{' not in gcode
    assert '}' not in gcode


def test_cura_printer_emits_heat_command():
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name=_CURA_PRINTER, initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert _HEAT_RE.search(gcode) is not None
    # the user-supplied temperatures should appear in the generated gcode
    assert '210' in gcode
    assert '60' in gcode


# --------------------------------------------------------------------------- #
# 3. safe_eval: allowed grammar evaluates, arbitrary code is rejected
# --------------------------------------------------------------------------- #

def test_safe_eval_reads_from_data():
    assert safe_eval("data['x']", {'x': 42}) == 42


def test_safe_eval_does_arithmetic():
    assert safe_eval('1+2', {}) == 3


def test_safe_eval_allows_int_call_and_multiplication():
    assert safe_eval('int(0.75*255)', {}) == 191


def test_safe_eval_combines_data_lookup_and_arithmetic():
    assert safe_eval("data['build_volume_y'] - 5", {'build_volume_y': 200}) == 195


def test_safe_eval_rejects_import(tmp_path):
    sentinel = tmp_path / 'pwned'
    payload = f"__import__('os').system('touch {sentinel}')"
    with pytest.raises(ValueError):
        safe_eval(payload, {})
    assert not sentinel.exists()


def test_safe_eval_rejects_attribute_access():
    with pytest.raises(ValueError):
        safe_eval('data.__class__', {'x': 1})


def test_safe_eval_rejects_unknown_name():
    with pytest.raises(ValueError):
        safe_eval('foo + 1', {})


# --------------------------------------------------------------------------- #
# 4. extra_functions: points_only
# --------------------------------------------------------------------------- #

def test_points_only_filters_non_points():
    steps = [fc.Point(x=0, y=0, z=0), fc.Extruder(on=False), fc.Point(x=1, y=1, z=1)]
    result = fc.points_only(steps, track_xyz=False)
    assert len(result) == 2
    assert all(isinstance(p, fc.Point) for p in result)


def test_points_only_no_track_keeps_undefined_attributes():
    # track_xyz=False returns points exactly as defined, including None attributes
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=5)]
    result = fc.points_only(steps, track_xyz=False)
    assert len(result) == 2
    assert result[1].x == 5
    assert result[1].y is None
    assert result[1].z is None


def test_points_only_track_fills_from_previous():
    # track_xyz=True propagates the most recent value into undefined attributes
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=5)]
    result = fc.points_only(steps, track_xyz=True)
    assert len(result) == 2
    assert (result[1].x, result[1].y, result[1].z) == (5, 0, 0)


def test_points_only_track_drops_leading_underdefined_points():
    # leading points without all of x/y/z defined are dropped when tracking
    steps = [fc.Point(x=1), fc.Point(y=2), fc.Point(x=3, y=4, z=5)]
    result = fc.points_only(steps, track_xyz=True)
    assert len(result) == 1
    assert (result[0].x, result[0].y, result[0].z) == (3, 4, 5)


def test_points_only_track_empty_when_never_fully_defined():
    # edge case: no point ever has all xyz defined -> empty list
    steps = [fc.Point(x=1), fc.Point(y=2)]
    assert fc.points_only(steps, track_xyz=True) == []


# --------------------------------------------------------------------------- #
# 5. extra_functions: relative_point
# --------------------------------------------------------------------------- #

def test_relative_point_from_point_reference():
    pt = fc.relative_point(fc.Point(x=1, y=2, z=3), 10, 20, 30)
    assert (pt.x, pt.y, pt.z) == (11, 22, 33)


def test_relative_point_uses_last_point_in_list():
    reference = [fc.Point(x=1, y=1, z=1), fc.Point(x=5, y=5, z=5)]
    pt = fc.relative_point(reference, 1, 2, 3)
    assert (pt.x, pt.y, pt.z) == (6, 7, 8)


def test_relative_point_skips_trailing_non_points_in_list():
    reference = [fc.Point(x=5, y=5, z=5), fc.Extruder(on=False)]
    pt = fc.relative_point(reference, 1, 1, 1)
    assert (pt.x, pt.y, pt.z) == (6, 6, 6)


def test_relative_point_raises_on_underdefined_reference():
    with pytest.raises(Exception):
        fc.relative_point(fc.Point(x=1, y=2), 0, 0, 0)


def test_relative_point_raises_when_no_point_in_list():
    with pytest.raises(Exception):
        fc.relative_point([], 0, 0, 0)


# --------------------------------------------------------------------------- #
# 6. extra_functions: flatten
# --------------------------------------------------------------------------- #

def test_flatten_mixes_lists_and_scalars():
    assert fc.flatten([1, [2, 3], 4, [5]]) == [1, 2, 3, 4, 5]


def test_flatten_already_flat_is_unchanged():
    assert fc.flatten([1, 2, 3]) == [1, 2, 3]


def test_flatten_empty_list():
    assert fc.flatten([]) == []


# --------------------------------------------------------------------------- #
# 7. extra_functions: first_point / last_point
# --------------------------------------------------------------------------- #

def test_first_point_returns_first_fully_defined():
    steps = [fc.Point(x=1), fc.Point(x=2, y=2, z=2), fc.Point(x=3, y=3, z=3)]
    pt = fc.first_point(steps, fully_defined=True)
    assert (pt.x, pt.y, pt.z) == (2, 2, 2)


def test_first_point_not_fully_defined_returns_first_point():
    steps = [fc.Point(x=1), fc.Point(x=2, y=2, z=2)]
    pt = fc.first_point(steps, fully_defined=False)
    assert pt.x == 1


def test_first_point_raises_when_none_fully_defined():
    with pytest.raises(Exception):
        fc.first_point([fc.Point(x=1)], fully_defined=True)


def test_first_point_raises_when_no_point_present():
    with pytest.raises(Exception):
        fc.first_point([fc.Extruder(on=False)], fully_defined=False)


def test_last_point_returns_last_fully_defined():
    steps = [fc.Point(x=1, y=1, z=1), fc.Point(x=2, y=2, z=2), fc.Point(x=3)]
    pt = fc.last_point(steps, fully_defined=True)
    assert (pt.x, pt.y, pt.z) == (2, 2, 2)


def test_last_point_raises_when_none_fully_defined():
    with pytest.raises(Exception):
        fc.last_point([fc.Point(x=1)], fully_defined=True)


# --------------------------------------------------------------------------- #
# 8. extra_functions: linspace
# --------------------------------------------------------------------------- #

def test_linspace_zero_points_is_empty():
    assert fc.linspace(0, 10, 0) == []


def test_linspace_one_point_is_start_only():
    assert fc.linspace(0, 10, 1) == [0]


def test_linspace_two_points_are_endpoints():
    assert fc.linspace(0, 10, 2) == [0.0, 10.0]


def test_linspace_normal_is_evenly_spaced_and_inclusive():
    result = fc.linspace(0, 10, 5)
    assert result == [0.0, 2.5, 5.0, 7.5, 10.0]
    assert result[0] == 0
    assert result[-1] == 10


# --------------------------------------------------------------------------- #
# 9. extra_functions: travel_to
# --------------------------------------------------------------------------- #

def test_travel_to_wraps_point_in_extruder_toggle():
    steps = fc.travel_to(fc.Point(x=1, y=2, z=3))
    assert isinstance(steps, list)
    assert len(steps) == 3
    assert isinstance(steps[0], fc.Extruder)
    assert isinstance(steps[1], fc.Point)
    assert isinstance(steps[2], fc.Extruder)
    # extruder is turned off before the move and back on after it
    assert steps[0].on is False
    assert steps[2].on is True
    assert (steps[1].x, steps[1].y, steps[1].z) == (1, 2, 3)


# --------------------------------------------------------------------------- #
# 10. export_design / import_design round-trip
# --------------------------------------------------------------------------- #

def test_export_import_round_trip_preserves_types_and_values(tmp_path):
    steps = [
        fc.Point(x=0, y=0, z=0.2),
        fc.Extruder(on=False),
        fc.Point(x=10, y=5, z=0.4),
    ]
    base = str(tmp_path / 'design')
    fc.export_design(steps, base)
    assert os.path.exists(base + '.json')

    restored = fc.import_design(fc, base)
    assert [type(s).__name__ for s in restored] == ['Point', 'Extruder', 'Point']
    assert (restored[0].x, restored[0].y, restored[0].z) == (0, 0, 0.2)
    assert restored[1].on is False
    assert (restored[2].x, restored[2].y, restored[2].z) == (10, 5, 0.4)


def test_imported_design_transforms_to_gcode(tmp_path):
    # a round-tripped design must still be usable by the gcode pipeline
    steps = _simple_design()
    base = str(tmp_path / 'design')
    fc.export_design(steps, base)
    restored = fc.import_design(fc, base)
    gcode = fc.transform(
        restored,
        'gcode',
        fc.GcodeControls(printer_name='generic', initialization_data=dict(_INIT_DATA)),
        show_tips=False,
    )
    assert 'G1' in gcode


# --------------------------------------------------------------------------- #
# 11. custom printer: extruder-mode line is always emitted
# --------------------------------------------------------------------------- #

def test_custom_printer_emits_extruder_mode_without_overrides():
    gcode = fc.transform(
        _simple_design(),
        'gcode',
        fc.GcodeControls(printer_name='custom', initialization_data={}),
        show_tips=False,
    )
    assert ('M82' in gcode) or ('M83' in gcode)
