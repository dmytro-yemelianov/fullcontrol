"""Open registry of transform backends.

A backend turns a (fixed) step list + controls into a result. transform() looks the
result_type up here instead of hard-coding an if/elif, so new backends (e.g. a future
'simulation' or a non-3DP machine) plug in with register_backend(...) and need no
change to transform().
"""
_BACKENDS = {}


def register_backend(result_type, controls_class, runner):
    '''Register a transform backend.

    Args:
        result_type (str): the value passed as transform(..., result_type=...).
        controls_class: the Controls class to instantiate when the caller passes none.
        runner: callable(steps, controls, show_tips) -> result.
    '''
    _BACKENDS[result_type] = (controls_class, runner)


def get_backend(result_type):
    'Return (controls_class, runner) for result_type, or raise a clear error.'
    try:
        return _BACKENDS[result_type]
    except KeyError:
        raise ValueError(
            f"result_type {result_type!r} not recognized; available: {sorted(_BACKENDS)}"
        ) from None


def available_backends():
    'List the registered result_type names.'
    return sorted(_BACKENDS)
