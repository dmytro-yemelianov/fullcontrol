"""HIGH-1: gcode start/end template substitution must not execute arbitrary code.

The legacy implementation used `eval()` on every `{...}` term found in a printer's
start/end gcode, which is arbitrary code execution sourced from printer config /
user-overridable data. These tests pin the safe behaviour:
  - real template expressions still evaluate correctly
  - anything outside the small allowed grammar raises ValueError instead of running
"""
import pytest

from fullcontrol.gcode.import_printer import safe_eval, replace_gcode_variables


def test_safe_eval_supports_real_template_expressions():
    assert safe_eval("110", {}) == 110
    assert safe_eval("0.2", {}) == 0.2
    assert safe_eval("0+2", {}) == 2
    assert safe_eval("int(0.75*255)", {}) == 191
    assert safe_eval("data['nozzle_temp']", {'nozzle_temp': 210}) == 210
    assert safe_eval("data['build_volume_y'] - 5", {'build_volume_y': 200}) == 195


def test_safe_eval_blocks_arbitrary_code(tmp_path):
    sentinel = tmp_path / 'pwned'
    payload = f"__import__('os').system('touch {sentinel}')"
    with pytest.raises(ValueError):
        safe_eval(payload, {})
    assert not sentinel.exists()


def test_safe_eval_blocks_attribute_access(tmp_path):
    # dunder / attribute traversal must not be reachable
    with pytest.raises(ValueError):
        safe_eval("data.__class__", {'x': 1})


def test_replace_gcode_variables_substitutes_real_values():
    data = {'start_gcode': "M104 S{data['nozzle_temp']}", 'nozzle_temp': 215}
    replace_gcode_variables('any_printer', 'start_gcode', data)
    assert data['start_gcode'] == 'M104 S215'


def test_replace_gcode_variables_does_not_execute_code(tmp_path):
    sentinel = tmp_path / 'pwned'
    data = {'start_gcode': f"M104 S{{__import__('os').system('touch {sentinel}')}}"}
    with pytest.raises(ValueError):
        replace_gcode_variables('any_printer', 'start_gcode', data)
    assert not sentinel.exists()
