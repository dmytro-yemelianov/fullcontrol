"""Multiaxis backends (XYZB/XYZBC/XYZC0B1) after sharing a Printer base + gcode driver."""
import pytest

import lab.fullcontrol.fouraxis as fc4
import lab.fullcontrol.fiveaxis as fc5
import lab.fullcontrol.fiveaxisC0B1 as fc51
from lab.fullcontrol.multiaxis.gcode._base import MultiaxisPrinter

INIT = {'nozzle_temp': 210, 'bed_temp': 60}


def test_xyzb_transform_produces_gcode():
    steps = [fc4.Point(x=0, y=0, z=0, b=0), fc4.Extruder(on=True), fc4.Point(x=10, y=0, z=2, b=30)]
    g = fc4.transform(steps, 'gcode', fc4.GcodeControls(b_offset_z=5, initialization_data=INIT))
    assert 'G1' in g and 'B30' in g


def test_xyzbc_transform_produces_gcode():
    steps = [fc5.Point(x=0, y=0, z=0, b=0, c=0), fc5.Extruder(on=True), fc5.Point(x=10, y=0, z=2, b=30, c=45)]
    g = fc5.transform(steps, 'gcode', fc5.GcodeControls(bc_intercept=fc5.Point(x=2, y=0, z=1), initialization_data=INIT))
    assert 'G1' in g and 'C45' in g


def test_xyzc0b1_transform_produces_gcode():
    steps = [fc51.Point(x=0, y=0, z=0, b=0, c=0), fc51.Extruder(on=True), fc51.Point(x=10, y=0, z=2, b=30, c=45)]
    g = fc51.transform(steps, 'gcode', fc51.GcodeControls(b_offset_z=5, initialization_data=INIT))
    assert 'G1' in g


def test_xyzb_requires_b_offset_z():
    with pytest.raises(Exception, match='b_offset_z'):
        fc4.transform([fc4.Point(x=0, y=0, z=0, b=0)], 'gcode', fc4.GcodeControls())


def test_all_multiaxis_printers_share_base():
    from lab.fullcontrol.multiaxis.gcode.XYZB.printer import Printer as P4
    from lab.fullcontrol.multiaxis.gcode.XYZBC.printer import Printer as P5
    from lab.fullcontrol.multiaxis.gcode.XYZC0B1.printer import Printer as P51
    assert all(issubclass(p, MultiaxisPrinter) for p in (P4, P5, P51))


def test_step_error_names_offending_step_in_multiaxis_driver():
    # a registered step that raises (PrinterCommand with an unknown id -> KeyError) gets context
    steps = [fc4.Point(x=0, y=0, z=0, b=0), fc4.Extruder(on=True),
             fc4.Point(x=1, y=0, z=0, b=0), fc4.PrinterCommand(id='no_such_command_xyz')]
    with pytest.raises(Exception, match='PrinterCommand'):
        fc4.transform(steps, 'gcode', fc4.GcodeControls(b_offset_z=5, initialization_data=INIT))
