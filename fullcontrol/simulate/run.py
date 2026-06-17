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


def simulate(steps, controls, show_tips=True) -> SimulationResult:
    '''Simulate a design and return a SimulationResult. `controls` is a GcodeControls (the
    simulation reflects the gcode that would be produced, including the printer's start/end
    procedures and primer).'''
    return simulate_from_ir(resolve(steps, controls))
