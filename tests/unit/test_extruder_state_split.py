"""The Extruder *step* carries only design data; the gcode backend's running extruder
accumulators (volume_to_e, total_volume, retracted_length, ...) and emission methods live on
a separate ExtruderState. This keeps the user-facing step a pure data object.
"""
import fullcontrol as fc
from fullcontrol.gcode.extrusion_classes import Extruder, ExtruderState

_RUNTIME = {'volume_to_e', 'total_volume', 'total_volume_ref', 'travel_format',
            'retraction_distance', 'retraction_speed', 'retracted_length'}
_DESIGN = {'on', 'units', 'dia_feed', 'relative_gcode'}


def test_step_extruder_is_design_only():
    fields = set(Extruder.model_fields)
    assert _DESIGN <= fields
    assert not (_RUNTIME & fields), f'runtime fields leaked onto the step: {_RUNTIME & fields}'
    # and the emission methods are not on the step
    assert not hasattr(Extruder, 'get_and_update_volume')
    assert not hasattr(Extruder, 'e_gcode')


def test_extruder_state_holds_runtime_and_methods():
    fields = set(ExtruderState.model_fields)
    assert _RUNTIME <= fields
    assert _DESIGN <= fields  # it still receives design fields via update_from
    assert hasattr(ExtruderState, 'get_and_update_volume')
    assert hasattr(ExtruderState, 'e_gcode')
    assert hasattr(ExtruderState, 'update_e_ratio')


def test_combined_extruder_no_longer_exposes_runtime():
    assert not (_RUNTIME & set(fc.Extruder.model_fields))


def test_extrusion_still_works_end_to_end():
    g = fc.transform([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)],
                     'gcode', fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210}),
                     show_tips=False)
    assert 'E' in g  # an extruding move emits an E value
