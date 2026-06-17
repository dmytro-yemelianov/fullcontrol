"""Optimization-pass showcase - a travel-heavy design + a before/after report.

`towers_grid` prints a grid of separate square-wall towers, hopping between them with the extruder
off (long travels) and tracing each tower's edges as several collinear points. That gives the IR->IR
optimization passes (fullcontrol/ir/passes.py) real work to do:
  - `merge_collinear` collapses the subdivided straight edges into single moves (smaller g-code),
  - `retract_on_travel` inserts a retraction/unretraction around each long inter-tower travel (anti-
    stringing).

`optimization_report` resolves the design with and without the passes and returns the segment count,
the number of retraction events inserted, and the simulation summary - so you can see the passes
working. Passes are opt-in (`initialization_data['optimize']`), so they never change default output.
"""
import fullcontrol as fc


def towers_grid(rows: int = 2, cols: int = 2, tower_size: float = 12.0, spacing: float = 30.0,
                layers: int = 6, points_per_edge: int = 6, layer_height: float = 0.24,
                extrusion_width: float = 0.6, centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """A `rows` x `cols` grid of separate square-wall towers, with extruder-off travels between them
    and each square edge subdivided into `points_per_edge` collinear points."""
    cx, cy = centre
    s = tower_size / 2.0
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=layer_height)]
    for r in range(rows):
        for c in range(cols):
            tx = cx + (c - (cols - 1) / 2.0) * spacing
            ty = cy + (r - (rows - 1) / 2.0) * spacing
            corners = [(tx - s, ty - s), (tx + s, ty - s), (tx + s, ty + s), (tx - s, ty + s), (tx - s, ty - s)]
            steps.append(fc.Extruder(on=False))                       # travel to this tower
            steps.append(fc.Point(x=corners[0][0], y=corners[0][1], z=first_layer_gap))
            steps.append(fc.Extruder(on=True))
            for layer in range(layers):
                z = first_layer_gap + layer * layer_height
                for k in range(4):                                    # 4 subdivided edges per layer
                    (ax, ay), (bx, by) = corners[k], corners[k + 1]
                    for j in range(1, points_per_edge + 1):
                        f = j / points_per_edge
                        steps.append(fc.Point(x=ax + (bx - ax) * f, y=ay + (by - ay) * f, z=z))
    return steps


def optimization_report(steps: list, min_travel: float = 5.0) -> dict:
    '''Resolve `steps` with and without the optimization passes and report the difference:
    {baseline, optimized} each with segment count, retraction-event count, and sim summary.'''
    from fullcontrol.ir import resolve, Segment
    from fullcontrol.simulate.run import simulate_from_ir

    def stats(optimize):
        init = {'nozzle_temp': 210}
        if optimize:
            init = {**init, 'optimize': optimize}
        controls = fc.GcodeControls(printer_name='generic', initialization_data=init)
        tp = resolve(steps, controls)
        segments = sum(1 for e in tp.events if isinstance(e, Segment))
        retractions = sum(1 for e in tp.events if type(e).__name__ in ('Retraction', 'Unretraction'))
        return {'segments': segments, 'retractions': retractions,
                'sim': simulate_from_ir(tp).summary()}

    return {
        'baseline': stats(None),
        'optimized': stats(['merge_collinear', ('retract_on_travel', {'min_distance': min_travel})]),
    }


if __name__ == '__main__':
    rep = optimization_report(towers_grid())
    print(f"baseline : {rep['baseline']['segments']} segments, "
          f"{rep['baseline']['retractions']} retractions")
    print(f"optimized: {rep['optimized']['segments']} segments "
          f"(merge_collinear), {rep['optimized']['retractions']} retractions (retract_on_travel)")
