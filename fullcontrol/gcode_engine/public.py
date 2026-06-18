"""The public verification entry point: `verify_gcode(text) -> VerificationReport`.

Lifts arbitrary g-code to the Toolpath IR (via the Phase-1 parser), runs the 8 reused design-time
validation rules (over `validate_toolpath`) plus the new external-g-code rules, optionally attaches
a `SimulationResult`, and aggregates everything into a `VerificationReport`.
"""
from fullcontrol.gcode_engine.detector import ParseParams
from fullcontrol.gcode_engine.parser import parse_gcode
from fullcontrol.gcode_engine.verification import VerificationReport
from fullcontrol.gcode_engine.rules import NEW_RULES


def verify_gcode(text, *, params=None, rules=None, simulate=True, build_volume=None,
                 max_flow_mm3s=15.0) -> VerificationReport:
    '''Verify arbitrary g-code and return a structured `VerificationReport`.

    Args:
        text: the g-code as a single string.
        params: a `ParseParams` for parsing; detected from the text when omitted.
        rules: an iterable of new-rule names to run (default: all). The 8 reused validation rules
            always run. Unknown names are ignored.
        simulate: when True, attach a `SimulationResult` (segment/time/flow metrics) to the report.
        build_volume: optional (x, y, z) build volume to enable the out-of-bounds check on g-code
            whose printer/build volume is otherwise unknown.
        max_flow_mm3s: the volumetric flow ceiling for `flow_rate_ceiling` (default 15 for 0.4 mm).

    Returns:
        A `VerificationReport` with `.issues` (Issues carrying line/segment_index/suggested_fix),
        `.parse_params`, optional `.simulation`, and `.errors`/`.warnings`/`.ok`/`.summary()`/
        `.raise_if_errors()`.
    '''
    if params is None:
        params = ParseParams.detect(text)
    toolpath = parse_gcode(text, params)

    report = VerificationReport(parse_params=params)

    # context shared by the new rules
    init = _build_init(build_volume, params)
    ctx = {
        'init': init,
        'build_volume': build_volume,
        'max_flow_mm3s': max_flow_mm3s,
        'default_width': params.dia_feed and 0.4,  # nozzle-line default for the overhang heuristic
        'base_z': _first_extruding_z(toolpath),     # the bed/first-layer z anchors layer bucketing
    }

    # 1. the 8 reused design-time validation rules, over the parsed Toolpath
    from fullcontrol.validate.run import validate_toolpath
    from fullcontrol.validate.result import ValidationResult
    vr = ValidationResult()
    validate_toolpath(toolpath, init, vr)
    oob_loc = _first_out_of_bounds(toolpath, build_volume)  # (segment_index, line) or None
    for i in vr.issues:
        # enrich the reused out-of-bounds error with the offending segment's line number, which the
        # vectorised columnar check does not itself carry
        if oob_loc is not None and 'build volume' in i['message']:
            report.add(i['severity'], 'validate', i['message'],
                       line=oob_loc[1], segment_index=oob_loc[0])
        else:
            report.add(i['severity'], 'validate', i['message'])

    # 2. the new external-g-code rules
    selected = NEW_RULES if rules is None else {k: v for k, v in NEW_RULES.items() if k in set(rules)}
    for name, fn in selected.items():
        try:
            report.extend(fn(toolpath, params, ctx))
        except Exception as exc:  # a rule must never crash the whole verification
            report.add('info', name, f'rule raised and was skipped: {exc}')

    # 3. optional inline simulation
    if simulate:
        from fullcontrol.simulate.run import simulate_from_ir
        report.simulation = simulate_from_ir(toolpath)

    return report


def _first_extruding_z(toolpath):
    '''The z of the lowest extruding move - the first-layer height that anchors layer bucketing
    (layer 0 = base_z). Defaults to 0.0 when nothing extrudes.'''
    from fullcontrol.ir import Segment
    zs = [ev.end[2] for ev in toolpath.events
          if isinstance(ev, Segment) and not ev.travel and ev.length and ev.length > 0
          and ev.end[2] is not None]
    return min(zs) if zs else 0.0


def _first_out_of_bounds(toolpath, build_volume):
    'Return (segment_index, line) of the first move endpoint outside the build volume, or None.'
    if build_volume is None:
        return None
    bx, by, bz = build_volume
    from fullcontrol.ir import Segment
    idx = 0
    for ev in toolpath.events:
        if not isinstance(ev, Segment):
            continue
        x, y, z = ev.end
        out = ((x is not None and (x < 0 or x > bx))
               or (y is not None and (y < 0 or y > by))
               or (z is not None and (z < 0 or z > bz)))
        if out:
            return (idx, ev.source_index)
        idx += 1
    return None


def _build_init(build_volume, params):
    'Assemble the small init dict the reused validation rules read (build volume + retraction).'
    init = {'dia_feed': params.dia_feed, 'e_units': params.e_units}
    if build_volume is not None:
        init['build_volume_x'] = build_volume[0]
        init['build_volume_y'] = build_volume[1]
        init['build_volume_z'] = build_volume[2]
    return init
