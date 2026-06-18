"""`bead_studs` - the gallery design that showcases `fc.StationaryExtrusion` (extrude-in-place).

Mirrors tests/unit/test_examples.py: the design must resolve to gcode, simulate to a real print and
validate cleanly against a generous build volume. The KEY tests prove the distinguishing feature:
the step list contains one `fc.StationaryExtrusion` per stud, and the oozed (stationary) material
actually shows up in the simulated extruded volume.
"""
import fullcontrol as fc
from examples.bead_studs import bead_studs, braille_dots, _BRAILLE

_BUILD = {'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
          'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200}


def _controls(extra=None):
    return fc.GcodeControls(printer_name='generic', initialization_data={**_BUILD, **(extra or {})})


def _count_studs(steps):
    return sum(1 for s in steps if isinstance(s, fc.StationaryExtrusion))


def test_generates_gcode():
    steps = bead_studs(message='fc')
    gcode = fc.transform(steps, 'gcode', _controls(), show_tips=False)
    assert isinstance(gcode, str)
    assert gcode.count('\n') > 20          # a real toolpath, not a stub
    assert 'G1' in gcode                   # extruding moves (base) + stationary E-lines emitted


def test_simulates_to_a_real_print():
    steps = bead_studs(message='fc')
    r = fc.transform(steps, 'simulation', _controls(), show_tips=False)
    assert r.total_time_s > 0
    assert r.extruded_volume > 0           # material is actually deposited
    assert r.extruding_distance > 0        # the base plate provides moving extrusion


def test_validates_without_errors():
    steps = bead_studs(message='fc')
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


def test_grid_mode_validates():
    steps = bead_studs(rows=3, cols=4)
    r = fc.transform(steps, 'validate', _controls(), show_tips=False)
    assert r.ok, [e['message'] for e in r.errors]


# ---- the key tests: this design is *about* StationaryExtrusion -------------------------------

def test_grid_has_one_stationary_extrusion_per_stud():
    'A rows x cols grid emits exactly rows*cols StationaryExtrusion studs.'
    steps = bead_studs(rows=3, cols=4)
    assert _count_studs(steps) == 3 * 4


def test_braille_known_letters_map_to_right_dot_counts():
    "Grade-1 braille: 'f' is dots {1,2,4} (3 dots), 'c' is {1,4} (2 dots), 'a' is {1} (1 dot)."
    assert len(braille_dots('a')) == 1
    assert len(braille_dots('c')) == 2
    assert len(braille_dots('f')) == 3
    # the message's stud count equals the total number of raised braille dots
    expected = len(_BRAILLE['f']) + len(_BRAILLE['c'])
    assert _count_studs(bead_studs(message='fc')) == expected == 5


# controls with NO primer, so the only material in the simulation is the design itself
# (the front_lines_then_y primer otherwise adds its own moving + stationary extrusion baseline).
def _bare_controls():
    return fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})


def test_stationary_volume_shows_up_in_simulation():
    'The volume oozed in place (no XY motion) is real material: it appears in extruded_volume.'
    n, vol = 6, 2.5
    # base_layers=0 -> the design extrudes ONLY in place; no-primer controls keep it isolated
    steps = bead_studs(rows=2, cols=3, stud_volume=vol, base_layers=0)
    assert _count_studs(steps) == n
    r = fc.transform(steps, 'simulation', _bare_controls(), show_tips=False)
    assert r.extruding_distance == 0                       # nothing is extruded by moving
    assert abs(r.extruded_volume - n * vol) < 1e-6         # all volume is the stationary ooze
    assert r.filament_length > 0                           # the ooze advances filament


def test_stud_volume_scales_extruded_volume():
    'The stationary-deposited material scales linearly with stud_volume (primer cancels in the delta).'
    rb = fc.transform(bead_studs(rows=2, cols=2, stud_volume=1.0, base_layers=0),
                      'simulation', _controls(), show_tips=False)
    rd = fc.transform(bead_studs(rows=2, cols=2, stud_volume=2.0, base_layers=0),
                      'simulation', _controls(), show_tips=False)
    # 4 studs, +1.0 mm^3 each between the two runs -> +4.0 mm^3 total (everything else identical)
    assert abs((rd.extruded_volume - rb.extruded_volume) - 4.0) < 1e-6
