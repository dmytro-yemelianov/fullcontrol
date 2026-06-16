"""Visualization of native arc moves: an fc.Arc tessellates into points so the plot draws
the real curve (not a straight chord), reusing the Point rendering path for colour/bounds.
"""
from math import hypot

import fullcontrol as fc


def _plot_data(steps):
    return fc.transform(steps, 'plot',
                        fc.PlotControls(raw_data=True, printer_name='generic',
                                        initialization_data={'nozzle_temp': 210}),
                        show_tips=False)


def _arc_design(segments=100):
    return [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
            fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10),
                   direction='anticlockwise', segments=segments)]


def test_arc_adds_segment_points_to_the_path():
    pd = _plot_data(_arc_design(segments=20))
    path = pd.paths[-1]
    # 1 start point + 20 tessellated points
    assert len(path.xvals) == 21


def test_tessellated_points_lie_on_the_circle():
    pd = _plot_data(_arc_design(segments=40))
    path = pd.paths[-1]
    # plot coords are stored rounded to 3 dp, so allow for that rounding
    for x, y in zip(path.xvals[1:], path.yvals[1:]):  # skip the start vertex
        assert abs(hypot(x, y) - 10) < 2e-3


def test_last_tessellated_point_is_the_arc_end():
    pd = _plot_data(_arc_design(segments=30))
    path = pd.paths[-1]
    assert abs(path.xvals[-1] - 0) < 1e-6
    assert abs(path.yvals[-1] - 10) < 1e-6


def test_point_count_total_includes_arc_segments():
    from fullcontrol.visualize.state import State
    from fullcontrol.visualize.controls import PlotControls
    steps = _arc_design(segments=25)
    state = State(steps, PlotControls(printer_name='generic'))
    # 1 explicit Point + 25 arc segments
    assert state.point_count_total == 26


def test_bounding_box_encloses_the_arc_bulge():
    # the quarter arc from (10,0) to (0,10) bulges to x,y up to 10 even though the only
    # explicit point is (10,0); the bounding box must cover the swept region
    pd = _plot_data(_arc_design(segments=50))
    bb = pd.bounding_box
    assert bb.maxy >= 10 - 1e-6
    assert bb.maxx >= 10 - 1e-6


def test_helical_arc_ramps_z_across_tessellation():
    steps = [fc.Point(x=10, y=0, z=0.2), fc.Extruder(on=True),
             fc.Arc(centre=fc.Point(x=0, y=0), end=fc.Point(x=0, y=10, z=1.2),
                    direction='anticlockwise', segments=10)]
    pd = _plot_data(steps)
    path = pd.paths[-1]
    assert abs(path.zvals[1] - 0.3) < 1e-6     # first segment: 0.2 + (1.0)*(1/10)
    assert abs(path.zvals[-1] - 1.2) < 1e-6    # ends at the arc end z
