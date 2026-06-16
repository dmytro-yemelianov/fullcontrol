"""First-class Retraction / Unretraction step objects (explicit E-based retraction).

These complement the firmware-retraction route (PrinterCommand(id='retract') -> G10).
A Retraction emits an explicit 'G1 F<speed> E-<dist>' move; the designer specifies the
retraction distance in filament-mm (the slicer convention) and the renderer converts it
to the gcode E units, so a retract followed by a prime nets to zero extruded material in
both relative and absolute extrusion modes.
"""
from types import SimpleNamespace

import fullcontrol as fc
from fullcontrol.gcode.renderers import render_gcode


def _gcode(steps, init=None):
    init = {'nozzle_temp': 210, **(init or {})}
    return fc.transform(steps, 'gcode',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def test_retraction_and_unretraction_are_exposed():
    assert hasattr(fc, 'Retraction') and hasattr(fc, 'Unretraction')


def test_retraction_emits_negative_e_move_at_default_distance():
    # generic printer: default retraction distance 1.0 mm filament, speed 2400 mm/min
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2), fc.Retraction()])
    assert 'E-1' in g                 # 1.0 mm of filament retracted
    assert 'F2400' in g               # default retraction feedrate
    assert '; retract' in g


def test_retraction_distance_and_speed_override():
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2), fc.Retraction(distance=5, speed=1800)])
    assert 'E-5' in g
    assert 'F1800' in g


def test_unretraction_primes_back_what_was_retracted():
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2),
                fc.Retraction(distance=3),
                fc.Point(x=10, y=10, z=0.2),
                fc.Unretraction()])               # no distance -> prime the retracted 3 mm
    retract = [ln for ln in g.splitlines() if 'retract' in ln and 'unretract' not in ln]
    unretract = [ln for ln in g.splitlines() if 'unretract' in ln]
    assert any('E-3' in ln for ln in retract)
    assert any('E3' in ln for ln in unretract)    # positive prime of the same amount


def test_unretraction_survives_an_intervening_extruder_step():
    # regression: an Extruder step between retract and unretract must not reset the tracked
    # retracted length (a real travel sequence toggles the extruder off then on again)
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
                fc.Point(x=10, y=0, z=0.2),
                fc.Retraction(distance=3),
                fc.Extruder(on=False), fc.Point(x=10, y=10, z=0.2),
                fc.Extruder(on=True), fc.Unretraction()])
    unretract = [ln for ln in g.splitlines() if 'unretract' in ln]
    assert len(unretract) == 1 and 'E3' in unretract[0]


def test_retract_then_unretract_nets_to_zero_extrusion_in_absolute_mode():
    # in absolute-E mode the cumulative E must be unchanged after retract+prime around a travel
    base = [fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)]
    init = {'relative_e': False}
    plain = _gcode(base + [fc.Point(x=10, y=10, z=0.2)], init)
    retracted = _gcode(base + [fc.Retraction(distance=4), fc.Point(x=10, y=10, z=0.2), fc.Unretraction()], init)

    def final_e(g):
        es = [ln.split('E')[-1] for ln in g.splitlines() if 'E' in ln and ln.startswith('G1')]
        return float(es[-1].split()[0]) if es else None

    assert abs(final_e(plain) - final_e(retracted)) < 1e-6


def test_retraction_does_not_change_gcode_for_designs_without_it():
    # a design with no Retraction step is byte-identical to before the feature existed
    g = _gcode([fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2)])
    assert 'retract' not in g


def test_renderer_handles_retraction_with_stub_state():
    state = SimpleNamespace(
        extruder=SimpleNamespace(on=False, volume_to_e=1.0, retraction_distance=1.0,
                                 retraction_speed=2400, retracted_length=0.0,
                                 total_volume=0.0, total_volume_ref=0.0, relative_gcode=True),
        printer=SimpleNamespace(speed_changed=False),
    )

    def get_and_update_volume(volume):
        state.extruder.total_volume += volume
        ret = state.extruder.total_volume - state.extruder.total_volume_ref
        state.extruder.total_volume_ref = state.extruder.total_volume
        return ret
    state.extruder.get_and_update_volume = get_and_update_volume

    line = render_gcode(fc.Retraction(distance=2), state)
    assert 'E-2' in line and 'retract' in line
    assert state.extruder.retracted_length == 2.0
    assert state.printer.speed_changed is True
