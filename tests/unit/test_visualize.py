"""Characterization tests for the FullControl VISUALIZE subsystem.

These tests pin down the *current* observable behaviour of the visualize
subsystem (tube meshing, bounding box, plot-data assembly, point colouring,
plot controls and the plotly raw-data path) so that future refactors can be
verified against a known-good baseline.

Set the headless CI flag at import time so nothing tries to open a browser or
requires kaleido for image export.
"""

import os

os.environ.setdefault("FULLCONTROL_CICD_TESTING", "headless")

import numpy as np
import pytest

import fullcontrol as fc
from fullcontrol.visualize.bounding_box import BoundingBox
from fullcontrol.visualize.controls import PlotControls
from fullcontrol.visualize.plot_data import PlotData
from fullcontrol.visualize.plotly import generate_mesh, plot
from fullcontrol.visualize.point import Point as VisualizePoint
from fullcontrol.visualize.state import State
from fullcontrol.visualize.tube_mesh import FlowTubeMesh, TubeMesh

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

# Keyword-only arguments shared by the simple TubeMesh constructions below.
TUBE_KW = dict(sides=4, rounding_strength=1.0, flat_sides=False, inplace_path=True)


def _normal_path():
    return np.array([[0, 0, 0], [5, 0, 0], [10, 0, 2], [7, 1, 1.5]], dtype=float)


def _coincident_path():
    # two successive points coincide -> zero-length segment
    return np.array([[0, 0, 0], [5, 0, 0], [5, 0, 0], [10, 0, 2]], dtype=float)


def _raw_state_and_data(color_type, steps):
    """Build an initialized PlotControls/State/PlotData trio for colour tests."""
    controls = PlotControls(raw_data=True, color_type=color_type)
    controls.initialize()
    state = State(steps, controls)
    plot_data = PlotData(steps, state)
    return state, plot_data, controls


# ---------------------------------------------------------------------------
# TubeMesh
# ---------------------------------------------------------------------------


def test_tubemesh_mesh_points_shape_and_dtype():
    path = _normal_path()
    mesh = TubeMesh(path, widths=0.5, heights=0.5, capped=False, **TUBE_KW)
    # one cross-section profile of `sides` points per path point, each point is 3D
    assert mesh.mesh_points.shape == (len(path) * mesh.sides, 3)
    assert mesh.mesh_points.dtype == np.float64


def test_tubemesh_no_nan_for_normal_path():
    mesh = TubeMesh(_normal_path(), widths=0.5, heights=0.5, capped=False, **TUBE_KW)
    assert not np.isnan(mesh.mesh_points).any()


def test_tubemesh_no_nan_for_coincident_points():
    # _safe_row_norm is meant to keep zero-length segments from producing NaN
    mesh = TubeMesh(_coincident_path(), widths=0.5, heights=0.5, capped=False, **TUBE_KW)
    assert not np.isnan(mesh.mesh_points).any()


def test_tubemesh_uncapped_triangle_count():
    path = _normal_path()
    mesh = TubeMesh(path, widths=0.5, heights=0.5, capped=False, **TUBE_KW)
    # two triangles per side per cylinder
    assert mesh.triangles.shape == (mesh.num_cylinders * mesh.sides * 2, 3)


def test_tubemesh_capped_adds_endcap_triangles_and_two_vertices():
    path = _normal_path()
    uncapped = TubeMesh(path, widths=0.5, heights=0.5, capped=False, **TUBE_KW)
    capped = TubeMesh(path, widths=0.5, heights=0.5, capped=True, **TUBE_KW)

    # capping appends exactly the two path endpoints as extra mesh vertices
    assert len(capped.mesh_points) == len(uncapped.mesh_points) + 2
    # each cap contributes `sides` triangles (a fan), two caps total
    assert len(capped.triangles) == len(uncapped.triangles) + 2 * uncapped.sides


def test_tubemesh_triangle_indices_in_range():
    mesh = TubeMesh(_normal_path(), widths=0.5, heights=0.5, capped=True, **TUBE_KW)
    # every triangle index must reference a real mesh point
    assert mesh.triangles.min() >= 0
    assert mesh.triangles.max() < len(mesh.mesh_points)


def test_tubemesh_2d_path_zero_pads_z():
    # 2D points must be promoted to 3D with z=0 by make_valid_path
    mesh = TubeMesh(
        [[0, 0], [5, 0], [10, 5]],
        widths=0.5,
        heights=0.5,
        sides=4,
        rounding_strength=1.0,
        flat_sides=False,
        capped=False,
        inplace_path=False,
    )
    assert mesh.path_points.shape == (3, 3)
    assert (mesh.path_points[:, 2] == 0).all()
    assert not np.isnan(mesh.mesh_points).any()


# ---------------------------------------------------------------------------
# BoundingBox
# ---------------------------------------------------------------------------


def test_bounding_box_normal_design():
    bb = BoundingBox()
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=4, z=2),
        fc.Point(x=-2, y=8, z=6),
    ]
    bb.calc_bounds(steps)
    assert (bb.minx, bb.maxx) == (-2, 10)
    assert (bb.miny, bb.maxy) == (0, 8)
    assert (bb.minz, bb.maxz) == (0, 6)
    assert bb.rangex == 12 and bb.rangey == 8 and bb.rangez == 6
    assert bb.midx == 4 and bb.midy == 4 and bb.midz == 3


def test_bounding_box_empty_design_has_zero_ranges():
    # recently fixed: an empty design must produce zero ranges, not a negative
    # sentinel-derived value.
    bb = BoundingBox()
    bb.calc_bounds([])
    assert bb.rangex == 0 and bb.rangey == 0 and bb.rangez == 0
    assert bb.minx == 0 and bb.maxx == 0
    assert bb.midx == 0 and bb.midy == 0 and bb.midz == 0


def test_bounding_box_2d_design_has_zero_z_range():
    # points with z=None must not contribute to z bounds; z range collapses to 0
    bb = BoundingBox()
    bb.calc_bounds([fc.Point(x=0, y=0, z=None), fc.Point(x=4, y=2, z=None)])
    assert bb.rangex == 4 and bb.rangey == 2
    assert bb.minz == 0 and bb.maxz == 0 and bb.rangez == 0


# ---------------------------------------------------------------------------
# transform(... 'plot', raw_data=True) -> PlotData
# ---------------------------------------------------------------------------


def test_transform_raw_data_returns_plot_data():
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=10, y=0, z=0)]
    result = fc.transform(steps, "plot", fc.PlotControls(raw_data=True), show_tips=False)
    assert isinstance(result, PlotData)


def test_transform_new_path_per_extruder_toggle():
    # extruder toggles on->off->on, so the design splits into three paths
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Extruder(on=False),
        fc.Point(x=10, y=10, z=0),
        fc.Extruder(on=True),
        fc.Point(x=0, y=10, z=0),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True), show_tips=False)
    assert len(pd.paths) == 3
    # extrude / travel / extrude
    assert [p.extruder.on for p in pd.paths] == [True, False, True]


def test_transform_path_point_counts():
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Point(x=10, y=10, z=0),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True), show_tips=False)
    assert len(pd.paths) == 1
    path = pd.paths[0]
    # three distinct points appended to the single path
    assert len(path.xvals) == 3
    assert len(path.yvals) == 3
    assert len(path.zvals) == 3
    assert path.xvals == [0, 10, 10]


def test_transform_travel_and_extrude_separation():
    # a travel move (extruder off) must end up on its own path, separate from
    # the surrounding extruding paths.
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=5, y=0, z=0),
        fc.Extruder(on=False),
        fc.Point(x=5, y=5, z=0),
        fc.Extruder(on=True),
        fc.Point(x=10, y=5, z=0),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True), show_tips=False)
    extrude_paths = [p for p in pd.paths if p.extruder.on]
    travel_paths = [p for p in pd.paths if not p.extruder.on]
    assert len(extrude_paths) == 2
    assert len(travel_paths) == 1


# ---------------------------------------------------------------------------
# Point.update_color colour types
# ---------------------------------------------------------------------------


def test_update_color_z_gradient_at_top_of_range():
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=0, y=0, z=10)]
    state, plot_data, controls = _raw_state_and_data("z_gradient", steps)
    # bounding box rangez is 10; a point at z=10 sits at the top of the gradient
    state.point.z = 10
    point = VisualizePoint(x=0, y=0, z=10)
    point.update_color(state, plot_data, controls)
    r, g, b = point.color
    assert r == 0
    assert 0.0 <= g <= 1.0
    assert g == pytest.approx(1.0)
    assert b == 1


def test_update_color_z_gradient_at_bottom_of_range():
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=0, y=0, z=10)]
    state, plot_data, controls = _raw_state_and_data("z_gradient", steps)
    state.point.z = 0
    point = VisualizePoint(x=0, y=0, z=0)
    point.update_color(state, plot_data, controls)
    r, g, b = point.color
    assert (r, b) == (0, 1)
    assert g == pytest.approx(0.0)


def test_update_color_print_sequence_endpoints():
    steps = [fc.Point(x=0, y=0, z=0), fc.Point(x=1, y=0, z=0), fc.Point(x=2, y=0, z=0)]
    state, plot_data, controls = _raw_state_and_data("print_sequence", steps)

    state.point_count_now = 0
    start = VisualizePoint()
    start.update_color(state, plot_data, controls)
    # at the start: red channel high (0.8), green 0, blue fixed at 1
    assert start.color == [0.8, 0, 1]

    state.point_count_now = state.point_count_total
    end = VisualizePoint()
    end.update_color(state, plot_data, controls)
    # at the end: red 0, green high (1.0), blue fixed at 1
    assert end.color == [0.0, 1.0, 1]


def test_update_color_random_blue_channels():
    steps = [fc.Point(x=0, y=0, z=0)]
    state, plot_data, controls = _raw_state_and_data("random_blue", steps)
    point = VisualizePoint()
    point.update_color(state, plot_data, controls)
    r, g, b = point.color
    # red channel is fixed at 0.1; green is a random value in [0, 1]
    assert r == 0.1
    assert 0.0 <= g <= 1.0
    # NOTE: blue channel is hard-coded to 2 (out of the usual 0-1 range). This
    # looks like a quirk/bug, but we assert the *current* documented behaviour
    # rather than 'fixing' it here.
    assert b == 2


def test_update_color_travel_when_extruder_off():
    steps = [fc.Point(x=0, y=0, z=0)]
    state, plot_data, controls = _raw_state_and_data("z_gradient", steps)
    state.extruder.on = False
    point = VisualizePoint()
    point.update_color(state, plot_data, controls)
    # travel colour is a fixed grey-pink regardless of colour_type
    assert point.color == [0.75, 0.5, 0.5]


# ---------------------------------------------------------------------------
# PlotControls.initialize() defaults
# ---------------------------------------------------------------------------


def test_plot_controls_initialize_defaults_for_plotting():
    # when not exporting raw data, initialize() fills in style + line_width
    controls = PlotControls()
    assert controls.style is None
    assert controls.line_width is None
    controls.initialize()
    assert controls.style == "tube"
    assert controls.line_width == 2


def test_plot_controls_initialize_skips_defaults_for_raw_data():
    # raw-data export leaves style/line_width untouched
    controls = PlotControls(raw_data=True)
    controls.initialize()
    assert controls.style is None
    assert controls.line_width is None


# ---------------------------------------------------------------------------
# plotly.py generate_mesh / plot raw path
# ---------------------------------------------------------------------------


def test_generate_mesh_produces_valid_mesh3d():
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Point(x=10, y=10, z=0.4),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True, style="tube"), show_tips=False)
    path = pd.paths[0]
    mesh = generate_mesh(path, 2.0, FlowTubeMesh, 4, 0.4, False)
    mesh3d = mesh.to_Mesh3d()
    # a plotly Mesh3d exposes x/y/z vertex coordinates and i/j/k triangle indices
    assert mesh3d.x is not None and mesh3d.y is not None and mesh3d.z is not None
    assert mesh3d.i is not None and mesh3d.j is not None and mesh3d.k is not None
    assert not np.isnan(mesh.mesh_points).any()


def test_plot_tube_style_headless_does_not_raise():
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Point(x=10, y=10, z=0.4),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True, style="tube"), show_tips=False)
    controls = PlotControls(style="tube")
    controls.initialize()
    # in headless mode plot() returns early (no browser / kaleido) without raising
    assert plot(pd, controls) is None


def test_plot_line_style_headless_does_not_raise():
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Extruder(on=False),
        fc.Point(x=10, y=10, z=0),
    ]
    pd = fc.transform(steps, "plot", fc.PlotControls(raw_data=True, style="line"), show_tips=False)
    controls = PlotControls(style="line")
    controls.initialize()
    assert plot(pd, controls) is None


def test_transform_full_plot_pipeline_headless_returns_none():
    # the non-raw transform path drives the full plotly pipeline; in headless
    # mode it must complete and return None.
    steps = [
        fc.Point(x=0, y=0, z=0),
        fc.Point(x=10, y=0, z=0),
        fc.Point(x=10, y=10, z=0.4),
    ]
    result = fc.transform(steps, "plot", fc.PlotControls(style="line"), show_tips=False)
    assert result is None
