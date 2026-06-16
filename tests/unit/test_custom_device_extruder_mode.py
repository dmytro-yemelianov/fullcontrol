"""HIGH-4: the 'custom' device must always set the extruder relative/absolute mode.

Every other singletool profile emits an Extruder(relative_gcode=...) step
unconditionally so the E mode (M82/M83) is deterministic. `custom` was the only one
that gated it on the user passing `relative_e`, so a plain custom print left the
extrusion mode unset.
"""
from fullcontrol.common import Extruder
import fullcontrol.devices.community.singletool.custom as custom


def _extruder_steps(init_data):
    return [s for s in init_data['starting_procedure_steps'] if isinstance(s, Extruder)]


def test_custom_emits_extruder_mode_without_user_override():
    init_data = custom.set_up(user_overrides={})
    steps = _extruder_steps(init_data)
    assert len(steps) == 1
    # custom overrides relative_e to False -> absolute extrusion mode
    assert steps[0].relative_gcode is False


def test_custom_respects_user_relative_e_override():
    init_data = custom.set_up(user_overrides={'relative_e': True})
    steps = _extruder_steps(init_data)
    assert len(steps) == 1
    assert steps[0].relative_gcode is True
