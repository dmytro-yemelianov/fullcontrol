"""Phase 1 foundation: uniform object model (pydantic v2 only) + control classes on BaseModelPlus."""
import pytest

import fullcontrol as fc
from fullcontrol.base import BaseModelPlus


# A1 — base model still validates unknown fields (pydantic v2 path)
def test_data_class_rejects_unknown_construction_field():
    with pytest.raises(Exception):
        fc.Point(x=1, y=2, z=3, not_a_field=4)


# I14 — control classes now use BaseModelPlus
def test_controls_subclass_base_model_plus():
    assert issubclass(fc.GcodeControls, BaseModelPlus)
    assert issubclass(fc.PlotControls, BaseModelPlus)


def test_gcode_controls_reject_unknown_field():
    with pytest.raises(Exception):
        fc.GcodeControls(printer_name='generic', no_such_field=123)


def test_plot_controls_reject_unknown_field():
    with pytest.raises(Exception):
        fc.PlotControls(style='line', bogus=1)


def test_controls_support_dict_access():
    c = fc.GcodeControls(printer_name='ender_3')
    assert c['printer_name'] == 'ender_3'   # __getitem__ from BaseModelPlus
    c['save_as'] = 'out'                     # __setitem__
    assert c.save_as == 'out'


def test_valid_controls_still_construct_and_transform():
    steps = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=5, y=0, z=0.2)]
    g = fc.transform(steps, 'gcode',
                     fc.GcodeControls(printer_name='generic',
                                      initialization_data={'nozzle_temp': 210},
                                      save_as=None, include_date=False),
                     show_tips=False)
    assert 'G1' in g
    # default construction (no args) must still work
    fc.PlotControls(style='tube', color_type='z_gradient', zoom=1.5)
    fc.GcodeControls()
