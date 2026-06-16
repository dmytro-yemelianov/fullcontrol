"""Run the simulation backend: walk the resolved step list and accumulate metrics."""
from fullcontrol.simulate.result import SimulationResult
from fullcontrol.simulate.renderers import render_simulate


def simulate(steps, controls, show_tips=True):
    '''Simulate a design and return a SimulationResult. `controls` is a GcodeControls
    (the simulation reflects the gcode that would be produced, including the printer's
    start/end procedures and primer).'''
    from fullcontrol.gcode.state import State
    controls.initialize()
    state = State(steps, controls)
    result = SimulationResult()
    for step in state.steps:
        render_simulate(step, state, result)
    return result
