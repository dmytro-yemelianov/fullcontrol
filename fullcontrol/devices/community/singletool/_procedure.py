"""Helpers to edit a procedure step list by content/marker rather than by a fragile
positional index. Derived printer profiles (e.g. cr_10, the toolchangers, prusa_i3)
patch a base profile's start procedure; keying those edits on a step's content means
they fail loudly with a clear message - rather than silently corrupting the output -
if the base profile's step order ever changes."""
from fullcontrol.gcode import ManualGcode, PrinterCommand


def manual_gcode_text(text):
    'predicate: a ManualGcode whose text exactly equals `text`'
    return lambda s: isinstance(s, ManualGcode) and s.text == text


def manual_gcode_startswith(prefix):
    'predicate: a ManualGcode whose text starts with `prefix`'
    return lambda s: isinstance(s, ManualGcode) and (s.text or '').startswith(prefix)


def printer_command(command_id):
    'predicate: a PrinterCommand with the given id'
    return lambda s: isinstance(s, PrinterCommand) and s.id == command_id


def _find(steps, predicate, description):
    for i, step in enumerate(steps):
        if predicate(step):
            return i
    raise ValueError(f'no procedure step matching {description!r}')


def replace_step(steps, predicate, new_step, description='step'):
    'replace the first step matching `predicate` with `new_step` (in place)'
    steps[_find(steps, predicate, description)] = new_step


def remove_step(steps, predicate, description='step'):
    'remove the first step matching `predicate` (in place) and return it'
    return steps.pop(_find(steps, predicate, description))


def insert_before(steps, predicate, new_steps, description='step'):
    'insert `new_steps` immediately before the first step matching `predicate` (in place)'
    i = _find(steps, predicate, description)
    steps[i:i] = list(new_steps)
