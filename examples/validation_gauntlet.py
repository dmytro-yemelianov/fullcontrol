"""A 'validation gauntlet' - a set of tiny designs, each crafted to trip ONE pre-flight
validation rule, and nothing else of interest. It doubles as living documentation of the
validator (fullcontrol/validate/run.py): run any entry through the 'validate' backend and you
see exactly the warning/error it demonstrates.

Each design is intentionally minimal - just enough points for validation to run (an empty design
raises 'No point found in steps...', so every entry defines at least one fully-specified Point).

Some rules depend on initialization_data rather than the steps alone, so this module ships two
companion dicts keyed by the same rule names:

  - validation_gauntlet() -> dict[str, list]: the steps that trip each rule.
  - INIT -> dict[str, dict]: the initialization_data each design needs. For example
    'out_of_bounds'/'negative_z' need a build volume (build_volume_x/y/z); 'cold_extrusion'
    deliberately has NO nozzle heating (no nozzle_temp, no Hotend step); the temperature rules
    set nozzle_temp so they do not also raise a spurious cold-extrusion warning.
  - EXPECTED -> dict[str, tuple[str, str]]: maps each rule to (severity, substring), documenting
    what each design demonstrates - severity is 'error'/'warning'/'info' and substring is text
    that must appear in that severity's messages. This makes the gauntlet self-checking.

Usage:
    import fullcontrol as fc
    from examples.validation_gauntlet import validation_gauntlet, INIT, EXPECTED
    steps = validation_gauntlet()['out_of_bounds']
    r = fc.transform(steps, 'validate',
                     fc.GcodeControls(printer_name='generic', initialization_data=INIT['out_of_bounds']),
                     show_tips=False)
    print(r.summary())  # -> shows the build-volume error
"""
import fullcontrol as fc

# a roomy build volume + a sane hotend temp: the default init for rules that are not themselves
# about bounds or heating, so those designs only trip their own rule.
_BV = {'build_volume_x': 200, 'build_volume_y': 200, 'build_volume_z': 200, 'nozzle_temp': 210}


def validation_gauntlet() -> dict:
    """Return {rule_name: steps} where each steps list trips exactly that one validation rule.

    See INIT for the initialization_data each entry expects, and EXPECTED for the (severity,
    substring) each entry demonstrates.
    """
    return {
        # out-of-bounds endpoint -> error mentioning 'build volume' (needs build_volume_* in INIT)
        'out_of_bounds': [
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=250, y=50, z=0.2)],
        # an endpoint below the bed -> warning 'negative z' (needs build_volume_* in INIT)
        'negative_z': [
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=-1)],
        # extruding with no heating evidence -> warning 'cold extrusion'
        # (INIT must NOT set nozzle_temp and there is no Hotend step)
        'cold_extrusion': [
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # hotend commanded above MAX_NOZZLE_TEMP_C (350C) -> warning mentioning 'nozzle'
        'nozzle_too_hot': [
            fc.Hotend(temp=400, wait=True),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # hotend commanded below MIN_FDM_NOZZLE_TEMP_C (150C) -> warning mentioning 'nozzle'
        'nozzle_too_cold': [
            fc.Hotend(temp=120, wait=True),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # bed commanded above MAX_BED_TEMP_C (150C) -> warning mentioning 'bed'
        'bed_too_hot': [
            fc.Buildplate(temp=200, wait=True),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # non-positive feedrate (would emit F0) -> error mentioning 'speed'
        'zero_speed': [
            fc.Printer(print_speed=0),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # feedrate above MAX_FEEDRATE_MM_MIN (60000) -> warning mentioning 'speed'
        'fast_speed': [
            fc.Printer(print_speed=120000),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # first extruding move at z<=0 -> warning 'first extrusion'
        'first_layer_z': [
            fc.Point(x=10, y=10, z=0), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0)],
        # Retraction never primed back -> warning 'retracted'
        'unbalanced_retraction': [
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2),
            fc.Retraction(distance=3)],
        # extruding with zero extrusion cross-section -> warning 'extrusion geometry'
        'zero_geometry': [
            fc.ExtrusionGeometry(width=0, height=0.2),
            fc.Point(x=10, y=10, z=0.2), fc.Extruder(on=True), fc.Point(x=20, y=10, z=0.2)],
        # design uses retraction elsewhere, but a long travel has none -> info 'stringing'
        'stringing': [
            fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True), fc.Point(x=10, y=0, z=0.2),
            fc.Retraction(distance=1), fc.Unretraction(),       # design clearly uses retraction
            fc.Point(x=10, y=2, z=0.2),
            fc.Extruder(on=False), fc.Point(x=80, y=80, z=0.2),  # long travel, no retraction
            fc.Extruder(on=True), fc.Point(x=80, y=81, z=0.2)],
    }


# initialization_data each design needs. cold_extrusion deliberately has NO nozzle_temp (so no
# heating command is emitted); everything else gets a build volume + nozzle_temp so it only trips
# its own rule. out_of_bounds/negative_z rely on the build_volume_* being present.
INIT = {
    'out_of_bounds': _BV,
    'negative_z': _BV,
    'cold_extrusion': {},                 # no heating -> cold extrusion fires
    'nozzle_too_hot': _BV,
    'nozzle_too_cold': _BV,
    'bed_too_hot': _BV,
    'zero_speed': _BV,
    'fast_speed': _BV,
    'first_layer_z': _BV,
    'unbalanced_retraction': _BV,
    'zero_geometry': _BV,
    'stringing': _BV,
}


# (severity, substring) that each design must produce - documents what it demonstrates.
EXPECTED = {
    'out_of_bounds': ('error', 'build volume'),
    'negative_z': ('warning', 'negative z'),
    'cold_extrusion': ('warning', 'cold extrusion'),
    'nozzle_too_hot': ('warning', 'nozzle'),
    'nozzle_too_cold': ('warning', 'nozzle'),
    'bed_too_hot': ('warning', 'bed'),
    'zero_speed': ('error', 'speed'),
    'fast_speed': ('warning', 'speed'),
    'first_layer_z': ('warning', 'first extrusion'),
    'unbalanced_retraction': ('warning', 'retracted'),
    'zero_geometry': ('warning', 'extrusion geometry'),
    'stringing': ('info', 'stringing'),
}


if __name__ == '__main__':
    for _rule, _steps in validation_gauntlet().items():
        _r = fc.transform(_steps, 'validate',
                          fc.GcodeControls(printer_name='generic', initialization_data=INIT[_rule]),
                          show_tips=False)
        _sev, _sub = EXPECTED[_rule]
        _hit = any(_sub in i['message'] for i in _r.issues if i['severity'] == _sev)
        print(f"{_rule:24s} -> expect {_sev}/{_sub!r}: {'OK' if _hit else 'MISSING'}")
