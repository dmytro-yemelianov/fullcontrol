"""Print-time / material study - sweep a design over one parameter and chart the simulation output.

A small analysis tool built on the `simulation` backend (which now runs through the Rust kernel,
so a sweep of many large designs stays fast). `sweep()` builds the design for each parameter value,
simulates it, and returns the metrics; `study_table()` formats them; `study_figure()` returns a
Plotly figure with print time and filament use against the swept parameter.

    from examples import spiral_vase
    from examples.print_time_study import sweep, study_table
    rows = sweep(spiral_vase, 'height', [10, 20, 30, 40])
    print(study_table(rows, 'height'))
"""
import fullcontrol as fc

_METRICS = ('total_time_s', 'print_time_s', 'travel_time_s', 'extruded_volume',
            'filament_length', 'segment_count', 'max_flow_rate')


def _default_controls():
    return fc.GcodeControls(printer_name='generic',
                            initialization_data={'nozzle_temp': 210, 'bed_temp': 40,
                                                 'primer': 'front_lines_then_y'})


def sweep(design_fn, param: str, values, controls=None, **fixed) -> list:
    '''Simulate `design_fn` once per value of `param`, holding `fixed` kwargs constant.

    Returns a list of dicts, one per value: {param: value, <each simulation metric>}.
    '''
    controls = controls or _default_controls()
    rows = []
    for value in values:
        steps = design_fn(**{param: value}, **fixed)
        r = fc.transform(steps, 'simulation', controls, show_tips=False)
        row = {param: value}
        row.update({m: getattr(r, m) for m in _METRICS})
        rows.append(row)
    return rows


def study_table(rows: list, param: str) -> str:
    'A fixed-width text table of the sweep (param, print time, filament, peak flow, segments).'
    header = f'{param:>10} | {"print_s":>9} | {"travel_s":>9} | {"filament_mm":>12} | ' \
             f'{"volume_mm3":>11} | {"peak_flow":>9} | {"segments":>9}'
    lines = [header, '-' * len(header)]
    for r in rows:
        lines.append(f'{r[param]:>10} | {r["print_time_s"]:>9.1f} | {r["travel_time_s"]:>9.1f} | '
                     f'{r["filament_length"]:>12.1f} | {r["extruded_volume"]:>11.1f} | '
                     f'{r["max_flow_rate"]:>9.3f} | {r["segment_count"]:>9}')
    return '\n'.join(lines)


def study_figure(rows: list, param: str, title: str = None):
    '''A Plotly figure: print time (left axis) and filament length (right axis) vs `param`.
    Returns the figure so the caller can .show() or .write_image(...).'''
    import plotly.graph_objects as go
    xs = [r[param] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[r['print_time_s'] for r in rows], name='print time (s)',
                             mode='lines+markers', yaxis='y1'))
    fig.add_trace(go.Scatter(x=xs, y=[r['filament_length'] for r in rows], name='filament (mm)',
                             mode='lines+markers', yaxis='y2'))
    fig.update_layout(
        title=title or f'print time & material vs {param}',
        xaxis=dict(title=param),
        yaxis=dict(title='print time (s)'),
        yaxis2=dict(title='filament (mm)', overlaying='y', side='right'),
        legend=dict(x=0.01, y=0.99), template='plotly_white', width=760, height=480)
    return fig


if __name__ == '__main__':
    from examples import spiral_vase
    rows = sweep(spiral_vase, 'height', [10, 20, 30, 40, 50])
    print(study_table(rows, 'height'))
