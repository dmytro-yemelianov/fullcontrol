"""Phase-4 optimisation passes for the g-code engine.

Each module registers an IR->IR pass (a pure function ``Toolpath -> Toolpath``) into the shared
registry in :mod:`fullcontrol.ir.passes` via ``register_pass`` as an import side effect, so once
this package is imported the new passes compose with the four built-ins (``merge_collinear``,
``retract_on_travel``, ``coasting``, ``z_hop``) through ``apply_passes`` exactly like them.

``Segment`` is frozen: every pass constructs *new* ``Segment``s and never mutates, preserving the
invariants the built-ins preserve (material conserved unless intended, no cross-layer reordering).
"""
from fullcontrol.gcode_engine.passes import arc_fit, travel_reorder, adaptive_speed, simplify  # noqa: F401

__all__ = ['arc_fit', 'travel_reorder', 'adaptive_speed', 'simplify']
