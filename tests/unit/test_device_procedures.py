"""Device-profile procedure editing by marker (replaces fragile index patching)."""
import pytest

from fullcontrol.gcode import ManualGcode, PrinterCommand, Hotend
from fullcontrol.devices.community.singletool import _procedure as P
import fullcontrol.devices.community.singletool.cr_10 as cr_10
import fullcontrol.devices.community.singletool.toolchanger_T1 as toolchanger_T1
import fullcontrol.devices.community.singletool.prusa_i3 as prusa_i3
import fullcontrol.devices.community.singletool.base_settings as base_settings


# ---- helper unit behaviour ----
def test_replace_step_by_marker():
    steps = [ManualGcode(text='a'), ManualGcode(text=';MAXX:1'), ManualGcode(text='b')]
    P.replace_step(steps, P.manual_gcode_startswith(';MAXX'), ManualGcode(text=';MAXX:9'))
    assert steps[1].text == ';MAXX:9' and len(steps) == 3


def test_remove_then_insert_before():
    steps = [PrinterCommand(id='home'), PrinterCommand(id='absolute_coords')]
    P.remove_step(steps, P.printer_command('home'))
    P.insert_before(steps, P.printer_command('absolute_coords'), [PrinterCommand(id='home')])
    assert [s.id for s in steps] == ['home', 'absolute_coords']


def test_missing_marker_raises_clear_error():
    with pytest.raises(ValueError, match='tool-select'):
        P.replace_step([ManualGcode(text='x')], P.manual_gcode_text('nope'),
                       ManualGcode(text='y'), description='tool-select command')


# ---- derived profiles still produce the intended output ----
def test_cr_10_overrides_build_volume_to_300():
    texts = [s.text for s in cr_10.set_up({})['starting_procedure_steps'] if isinstance(s, ManualGcode)]
    assert any(';MAXX:300' in t for t in texts)
    assert not any(';MAXX:220' in t for t in texts)


def test_toolchanger_T1_selects_tool_T1():
    texts = [s.text for s in toolchanger_T1.set_up({})['starting_procedure_steps'] if isinstance(s, ManualGcode)]
    assert 'T1' in texts and 'T0' not in texts


def test_prusa_i3_homes_after_temperatures():
    steps = prusa_i3.set_up({})['starting_procedure_steps']
    home_idx = next(i for i, s in enumerate(steps) if isinstance(s, PrinterCommand) and s.id == 'home')
    last_hotend_idx = max(i for i, s in enumerate(steps) if isinstance(s, Hotend))
    assert home_idx > last_hotend_idx


# ---- I8: unified chamber_temp key ----
def test_base_settings_uses_chamber_temp_not_enclosure_temp():
    assert 'chamber_temp' in base_settings.default_initial_settings
    assert 'enclosure_temp' not in base_settings.default_initial_settings
