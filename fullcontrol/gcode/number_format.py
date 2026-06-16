def fmt(value, dp: int = 6) -> str:
    '''Format a number for gcode output.

    Uses fixed-point notation with `dp` decimal places, then strips trailing zeros
    (and any trailing decimal point). This avoids scientific notation (e.g. ``1e-05``
    or ``1.23457e+06``) that most firmware rejects, while keeping lines compact.

    Examples: ``fmt(1.0) -> '1'``, ``fmt(0.00001) -> '0.00001'``, ``fmt(12.3456789) -> '12.345679'``.
    '''
    return f'{value:.{dp}f}'.rstrip('0').rstrip('.')
