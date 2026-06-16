"""Printer resolution extracted from State.__init__ (with a friendly unknown-printer error)."""
import pytest

import fullcontrol as fc
from fullcontrol.gcode.import_printer import resolve_initialization_data


def test_unknown_printer_raises_clear_error():
    with pytest.raises(ValueError, match='unknown printer_name'):
        resolve_initialization_data('definitely_not_a_printer', {})


def test_unknown_printer_surfaces_through_transform():
    with pytest.raises(ValueError, match='unknown printer_name'):
        fc.transform([fc.Point(x=0, y=0, z=0)], 'gcode',
                     fc.GcodeControls(printer_name='definitely_not_a_printer'), show_tips=False)


def test_resolver_singletool_profile():
    data = resolve_initialization_data('generic', {})
    assert 'starting_procedure_steps' in data and 'print_speed' in data


def test_resolver_cura_profile():
    data = resolve_initialization_data('Cura/Modix V3 BIG-120X', {'nozzle_temp': 210})
    assert 'starting_procedure_steps' in data
