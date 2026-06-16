"""Shared gcode driver loop for the multiaxis backends."""
from datetime import datetime


def run_gcode(state, save_as=None):
    '''Process a pre-built multiaxis State's steps into a gcode string. If save_as is
    given, write to a timestamped file and return None; otherwise return the string.'''
    # while loop (not for) because some steps may change the length of state.steps
    while state.i < len(state.steps):
        step = state.steps[state.i]
        try:
            gcode_line = step.gcode(state)
        except Exception as e:
            raise type(e)(f'error generating gcode for step {state.i} ({type(step).__name__}): {e}') from e
        if gcode_line is not None:
            state.gcode.append(gcode_line)
        state.i += 1
    gc = '\n'.join(state.gcode)

    if save_as is not None:
        with open(save_as + datetime.now().strftime("__%d-%m-%Y__%H-%M-%S.gcode"), 'w') as f:
            f.write(gc)
        return None
    return gc
