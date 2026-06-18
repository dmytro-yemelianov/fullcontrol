"""Command-line interface for the g-code verification & optimisation engine (Phase 5).

Three subcommands over a g-code file path (or ``-`` for stdin):

* ``verify``   - run :func:`verify_gcode`, print the report; exit 1 if it has errors, else 0.
* ``optimise`` - run :func:`optimise_gcode`, write the optimised g-code (``-o`` or stdout) and
  print the :class:`OptimisationReport` summary (or ``--json``) to stderr.
* ``inspect``  - parse + verify + simulate, print a concise summary (segments, time, material,
  bbox, issue counts).

Invoked as ``python -m fullcontrol.gcode_engine verify|optimise|inspect …`` (see ``__main__``).
Errors the user can cause (missing file, unknown pass) are reported to stderr without a traceback
and exit with code 2.
"""
import argparse
import json
import sys


def _read_input(path: str) -> str:
    'Read the g-code from a file path, or from stdin when path is "-".'
    if path == '-':
        return sys.stdin.read()
    with open(path, encoding='utf-8') as f:
        return f.read()


def _parse_triple(text: str, flag: str):
    'Parse an "X,Y,Z" string into a (float, float, float) tuple, or raise CliError.'
    parts = [p.strip() for p in text.split(',')]
    if len(parts) != 3:
        raise CliError(f'{flag} expects three comma-separated numbers X,Y,Z (got {text!r})')
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise CliError(f'{flag} expects numbers, got {text!r}')


def _split_list(text: str):
    'Split a comma-separated option value into a clean list, dropping empties.'
    return [p.strip() for p in text.split(',') if p.strip()]


class CliError(Exception):
    'A user-facing error: printed to stderr without a traceback, exits with code 2.'


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #

def _bbox(toolpath):
    '''The (min, max) bounding box over every defined Segment endpoint, as
    ``((minx, miny, minz), (maxx, maxy, maxz))``, or ``None`` when there are no moves.'''
    from fullcontrol.ir import Segment
    los = [None, None, None]
    his = [None, None, None]
    seen = False
    for ev in toolpath.events:
        if not isinstance(ev, Segment):
            continue
        for pt in (ev.start, ev.end):
            for k in range(3):
                v = pt[k]
                if v is None:
                    continue
                seen = True
                los[k] = v if los[k] is None else min(los[k], v)
                his[k] = v if his[k] is None else max(his[k], v)
    if not seen:
        return None
    lo = tuple(0.0 if v is None else v for v in los)
    hi = tuple(0.0 if v is None else v for v in his)
    return (lo, hi)


def _sim_dict(sim):
    'A SimulationResult as a plain JSON-serialisable dict (or None).'
    if sim is None:
        return None
    return {
        'total_time_s': sim.total_time_s,
        'print_time_s': sim.print_time_s,
        'travel_time_s': sim.travel_time_s,
        'extruding_distance': sim.extruding_distance,
        'travel_distance': sim.travel_distance,
        'extruded_volume': sim.extruded_volume,
        'filament_length': sim.filament_length,
        'segment_count': sim.segment_count,
        'max_flow_rate': sim.max_flow_rate,
    }


def _params_dict(params):
    'A ParseParams as a plain JSON-serialisable dict.'
    if params is None:
        return None
    keys = ('flavor', 'relative_e', 'e_units', 'dia_feed', 'travel_g1_e0')
    out = {}
    for k in keys:
        if hasattr(params, k):
            out[k] = getattr(params, k)
    return out


def _report_json(report):
    'The full verify report as a JSON object: issues + parse_params + simulation.'
    return {
        'ok': report.ok,
        'issues': [i.as_dict() for i in report.issues],
        'counts': {
            'errors': len(report.errors),
            'warnings': len(report.warnings),
            'infos': len(report.infos),
        },
        'parse_params': _params_dict(report.parse_params),
        'simulation': _sim_dict(report.simulation),
    }


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #

def _cmd_verify(args) -> int:
    from fullcontrol.gcode_engine.public import verify_gcode

    text = _read_input(args.file)
    build_volume = _parse_triple(args.build_volume, '--build-volume') if args.build_volume else None
    rules = _split_list(args.rules) if args.rules else None

    report = verify_gcode(
        text,
        rules=rules,
        simulate=not args.no_simulate,
        build_volume=build_volume,
        max_flow_mm3s=args.max_flow,
    )

    if args.json:
        print(json.dumps(_report_json(report), indent=2))
    else:
        print(report.summary())
    return 1 if report.errors else 0


def _cmd_optimise(args) -> int:
    from fullcontrol.gcode_engine.public import optimise_gcode
    from fullcontrol.ir.passes import available_passes

    text = _read_input(args.file)

    passes = None
    if args.passes:
        passes = _split_list(args.passes)
        known = set(available_passes())
        unknown = [p for p in passes if p not in known]
        if unknown:
            raise CliError(
                f'unknown optimisation pass(es): {", ".join(unknown)}. '
                f'Available: {", ".join(available_passes())}'
            )

    out_text, report = optimise_gcode(text, passes=passes, return_report=True)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out_text)
            if not out_text.endswith('\n'):
                f.write('\n')

    if args.json:
        payload = {
            'segments_before': report.segments_before,
            'segments_after': report.segments_after,
            'time_before_s': report.time_before_s,
            'time_after_s': report.time_after_s,
            'travel_before': report.travel_before,
            'travel_after': report.travel_after,
            'volume_before': report.volume_before,
            'volume_after': report.volume_after,
            'passes': [
                {
                    'name': p.name,
                    'segments_before': p.segments_before,
                    'segments_after': p.segments_after,
                    'time_before_s': p.time_before_s,
                    'time_after_s': p.time_after_s,
                    'travel_before': p.travel_before,
                    'travel_after': p.travel_after,
                    'volume_before': p.volume_before,
                    'volume_after': p.volume_after,
                }
                for p in report.passes
            ],
            'output': None if args.output else out_text,
        }
        print(json.dumps(payload, indent=2))
        if not args.output:
            # JSON already carries the g-code under "output"; nothing more to do.
            pass
    else:
        # the optimised g-code goes to stdout (unless -o); the report goes to stderr so the two
        # streams stay separable when piping.
        if not args.output:
            sys.stdout.write(out_text)
            if not out_text.endswith('\n'):
                sys.stdout.write('\n')
        print(report.summary(), file=sys.stderr)
    return 0


def _cmd_inspect(args) -> int:
    from fullcontrol.gcode_engine.detector import ParseParams
    from fullcontrol.gcode_engine.parser import parse_gcode
    from fullcontrol.gcode_engine.public import verify_gcode

    text = _read_input(args.file)
    params = ParseParams.detect(text)
    toolpath = parse_gcode(text, params)
    report = verify_gcode(text, params=params, simulate=True)
    sim = report.simulation
    box = _bbox(toolpath)

    if args.json:
        payload = {
            'parse_params': _params_dict(params),
            'simulation': _sim_dict(sim),
            'bbox': None if box is None else {'min': list(box[0]), 'max': list(box[1])},
            'counts': {
                'errors': len(report.errors),
                'warnings': len(report.warnings),
                'infos': len(report.infos),
            },
            'ok': report.ok,
        }
        print(json.dumps(payload, indent=2))
    else:
        lines = ['inspect: ' + args.file]
        if sim is not None:
            lines.append(
                f'  segments:  {sim.segment_count}'
            )
            lines.append(
                f'  time:      ~{sim.total_time_s:.1f}s '
                f'(print {sim.print_time_s:.1f}s, travel {sim.travel_time_s:.1f}s)'
            )
            lines.append(
                f'  material:  {sim.filament_length:.1f}mm filament, '
                f'{sim.extruded_volume:.1f}mm^3 deposited'
            )
            lines.append(
                f'  distance:  {sim.extruding_distance:.1f}mm extruding, '
                f'{sim.travel_distance:.1f}mm travel'
            )
            lines.append(f'  peak flow: {sim.max_flow_rate:.2f}mm^3/s')
        if box is not None:
            lo, hi = box
            lines.append(
                f'  bbox:      X[{lo[0]:.2f}, {hi[0]:.2f}] '
                f'Y[{lo[1]:.2f}, {hi[1]:.2f}] Z[{lo[2]:.2f}, {hi[2]:.2f}]'
            )
        lines.append(
            f'  issues:    {len(report.errors)} error(s), '
            f'{len(report.warnings)} warning(s), {len(report.infos)} info(s)'
        )
        print('\n'.join(lines))
    return 0


# --------------------------------------------------------------------------- #
# argument parsing & entry point
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    from fullcontrol.ir.passes import available_passes

    parser = argparse.ArgumentParser(
        prog='python -m fullcontrol.gcode_engine',
        description='Verify, optimise and inspect g-code with the FullControl engine.',
    )
    sub = parser.add_subparsers(dest='command', required=True, metavar='{verify,optimise,inspect}')

    # verify
    p_verify = sub.add_parser('verify', help='verify g-code and report issues (exit 1 on errors)')
    p_verify.add_argument('file', help='g-code file path, or "-" for stdin')
    p_verify.add_argument('--rules', help='comma-separated subset of new rule names to run')
    p_verify.add_argument('--build-volume', metavar='X,Y,Z',
                          help='build volume to enable the out-of-bounds check')
    p_verify.add_argument('--max-flow', type=float, default=15.0,
                          help='volumetric flow ceiling in mm^3/s (default 15)')
    p_verify.add_argument('--json', action='store_true', help='emit a JSON report')
    p_verify.add_argument('--no-simulate', action='store_true',
                          help='skip attaching simulation metrics')
    p_verify.set_defaults(func=_cmd_verify)

    # optimise
    avail = ', '.join(available_passes())
    p_opt = sub.add_parser('optimise', help='optimise g-code via IR passes')
    p_opt.add_argument('file', help='g-code file path, or "-" for stdin')
    p_opt.add_argument('--passes', help=f'comma-separated passes to run. Available: {avail}')
    p_opt.add_argument('-o', '--output', metavar='OUT.gcode',
                       help='write optimised g-code here (stdout if omitted)')
    p_opt.add_argument('--json', action='store_true',
                       help='emit a JSON report (g-code under "output" if no -o)')
    p_opt.set_defaults(func=_cmd_optimise)

    # inspect
    p_ins = sub.add_parser('inspect', help='parse + verify + simulate and print a summary')
    p_ins.add_argument('file', help='g-code file path, or "-" for stdin')
    p_ins.add_argument('--json', action='store_true', help='emit a JSON summary')
    p_ins.set_defaults(func=_cmd_inspect)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f'error: file not found: {exc.filename}', file=sys.stderr)
        return 2
    except ValueError as exc:
        # e.g. an unknown pass surfaced from resolve_specs/get_pass deeper in the stack
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':  # pragma: no cover - exercised via __main__.py / python -m
    sys.exit(main())
