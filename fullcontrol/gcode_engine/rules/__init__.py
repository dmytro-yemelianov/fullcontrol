"""Verification rules tuned for arbitrary (external + our own) g-code.

Each rule is a function ``rule(toolpath, params, ctx) -> list[Issue]`` that folds over a parsed
`Toolpath` (and/or a numpy `ColumnarToolpath` view) and returns `Issue`s with `line`
(1-based g-code line, taken from each Segment's `source_index`, which the parser repurposes as the
line number) and `segment_index` (0-based position in the Segment stream) populated where
applicable.

Rules that need extrusion `width`/`height` (which the parser cannot recover from E alone, so they
are ``None`` on bare external g-code) guard against ``None`` and skip those segments - so they
degrade to no-ops rather than producing false positives. `ctx` is a small dict of resolved context
(``init`` data, ``build_volume``, ``max_flow_mm3s``).

`REUSED` rules (bounds, negative-z, cold-extrusion, temp/speed sanity, first-layer-z, retraction
balance, zero-geometry, stringing) live in `fullcontrol/validate/run.py` and are invoked separately
via `validate_toolpath`; this package holds only the NEW external-g-code rules.
"""
from fullcontrol.gcode_engine.rules.geometry import overhang_angle, arc_opportunity
from fullcontrol.gcode_engine.rules.extrusion import flow_rate_ceiling, over_extrusion
from fullcontrol.gcode_engine.rules.travel import travel_density, seam_clustering, retraction_balance
from fullcontrol.gcode_engine.rules.adhesion import first_layer_adhesion
from fullcontrol.gcode_engine.rules.thermal import cooling_sanity, cold_extrusion

# the new-rule registry, by name (public.py merges these with the reused validate rules)
NEW_RULES = {
    'overhang_angle': overhang_angle,
    'arc_opportunity': arc_opportunity,
    'flow_rate_ceiling': flow_rate_ceiling,
    'over_extrusion': over_extrusion,
    'travel_density': travel_density,
    'seam_clustering': seam_clustering,
    'retraction_balance': retraction_balance,
    'first_layer_adhesion': first_layer_adhesion,
    'cooling_sanity': cooling_sanity,
    'cold_extrusion': cold_extrusion,
}

__all__ = ['NEW_RULES', 'overhang_angle', 'arc_opportunity', 'flow_rate_ceiling',
           'over_extrusion', 'travel_density', 'seam_clustering', 'retraction_balance',
           'first_layer_adhesion', 'cooling_sanity', 'cold_extrusion']
