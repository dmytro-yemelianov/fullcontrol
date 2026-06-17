"""The simulation backend, as a stateless fold over the Toolpath IR.

Instead of its own per-step state machine, simulation now resolves the design to the shared
Toolpath IR once (fullcontrol/ir) and accumulates metrics from it - pure arithmetic, no state.
"""
from fullcontrol.simulate.result import SimulationResult
from fullcontrol.ir import resolve, Segment, MaterialEvent


def simulate_from_ir(toolpath) -> SimulationResult:
    'Accumulate simulation metrics from a resolved Toolpath (the backend is a plain fold).'
    r = SimulationResult()
    for ev in toolpath.events:
        if isinstance(ev, Segment):
            if ev.speed and ev.length > 0:
                t = ev.length / ev.speed * 60.0  # mm / (mm/min) -> minutes -> seconds
                r.total_time_s += t
                if not ev.travel:
                    r.print_time_s += t
                    r.extruding_distance += ev.length
                    r.extruded_volume += ev.deposited_volume
                    r.filament_length += ev.filament_length
                    if t > 0:
                        r.max_flow_rate = max(r.max_flow_rate, ev.deposited_volume / t)
                else:
                    r.travel_time_s += t
                    r.travel_distance += ev.length
                r.segment_count += 1
        elif isinstance(ev, MaterialEvent):
            r.extruded_volume += ev.deposited_volume
            r.filament_length += ev.filament_length
    return r


def simulate_columnar(c) -> SimulationResult:
    '''Vectorised equivalent of `simulate_from_ir`, folding over a ColumnarToolpath with numpy
    reductions instead of a per-Segment Python loop. Sums are reordered by numpy's pairwise
    summation, so totals can differ from the object fold in the last bit(s); max_flow_rate (a max
    reduction) is order-independent and therefore identical.'''
    import numpy as np
    r = SimulationResult()
    valid = (c.speed != 0) & (c.length > 0)
    t = np.zeros_like(c.length)
    t[valid] = c.length[valid] / c.speed[valid] * 60.0  # mm / (mm/min) -> minutes -> seconds
    extrude = valid & ~c.travel
    travel = valid & c.travel
    r.total_time_s = float(t[valid].sum())
    r.print_time_s = float(t[extrude].sum())
    r.travel_time_s = float(t[travel].sum())
    r.extruding_distance = float(c.length[extrude].sum())
    r.travel_distance = float(c.length[travel].sum())
    r.extruded_volume = float(c.deposited_volume[extrude].sum()) + c.material_volume
    r.filament_length = float(c.filament_length[extrude].sum()) + c.material_filament
    r.segment_count = int(valid.sum())
    flow_mask = extrude & (t > 0)
    if flow_mask.any():
        r.max_flow_rate = float((c.deposited_volume[flow_mask] / t[flow_mask]).max())
    return r


def simulate(steps, controls, show_tips=True) -> SimulationResult:
    '''Simulate a design and return a SimulationResult. `controls` is a GcodeControls (the
    simulation reflects the gcode that would be produced, including the printer's start/end
    procedures and primer).

    Simulation only needs scalar metrics, so by default it takes the columnar fast-path
    (resolve straight into numpy columns, then a vectorised fold) - ~2.7x faster end-to-end on
    large designs. Optimisation passes run on the object IR, so when any are configured we fall
    back to the object path (resolve -> fold) to honour them.'''
    controls.initialize()
    optimize = (getattr(controls, 'initialization_data', None) or {}).get('optimize')
    if optimize:
        return simulate_from_ir(resolve(steps, controls))
    from fullcontrol.ir.columnar import resolve_columnar
    return simulate_columnar(resolve_columnar(steps, controls))
