"""The self-contained three.js viewer export (result_type='3d_html')."""
import json

import fullcontrol as fc
from examples import spiral_vase


def _design():
    return spiral_vase(height=3, segments_per_layer=24, lobes=4)


def _controls(**extra):
    return fc.PlotControls(initialization_data={'extrusion_width': 0.6, 'extrusion_height': 0.3}, **extra)


def _embedded_data(html: str) -> dict:
    'Pull the embedded `const DATA = {...};` JSON back out of the page.'
    for line in html.splitlines():
        line = line.strip()
        if line.startswith('const DATA = '):
            return json.loads(line[len('const DATA = '):].rstrip(';'))
    raise AssertionError('no embedded DATA found')


def test_3d_html_is_a_registered_backend():
    from fullcontrol.combinations.gcode_and_visualize.backends import available_backends
    assert '3d_html' in available_backends()


def test_export_returns_self_contained_html_with_threejs():
    html = fc.transform(_design(), '3d_html', _controls(), show_tips=False)
    assert html.lstrip().startswith('<!DOCTYPE html>')
    assert 'three.module.js' in html and 'importmap' in html  # three.js wired in
    assert 'OrbitControls' in html
    assert html.rstrip().endswith('</html>')


def test_embedded_geometry_matches_the_plot_data():
    design = _design()
    html = fc.transform(design, '3d_html', _controls(), show_tips=False)
    pd = fc.transform(design, 'plot', fc.PlotControls(raw_data=True,
                      initialization_data={'extrusion_width': 0.6, 'extrusion_height': 0.3}), show_tips=False)
    data = _embedded_data(html)
    expected_points = sum(len(p.xvals) for p in pd.paths if len(p.xvals) > 1)
    assert data['n_points'] == expected_points
    assert len(data['paths']) >= 1
    # each path's positions are flat xyz triples, colours (when present) match the vertex count
    for path in data['paths']:
        assert len(path['p']) % 3 == 0
        if path['c']:
            assert len(path['c']) == len(path['p'])


def test_embedded_colours_are_normalised_0_1():
    html = fc.transform(_design(), '3d_html', _controls(color_type='z_gradient'), show_tips=False)
    data = _embedded_data(html)
    vals = [v for path in data['paths'] for v in path['c']]
    assert vals, 'expected per-vertex colours'
    assert all(0.0 <= v <= 1.0 for v in vals)


def test_save_as_writes_a_file(tmp_path):
    out = tmp_path / 'vase'
    controls = fc.PlotControls(initialization_data={
        'extrusion_width': 0.6, 'extrusion_height': 0.3, 'save_as': str(out), 'title': 'My Vase'})
    html = fc.transform(_design(), '3d_html', controls, show_tips=False)
    written = tmp_path / 'vase.html'
    assert written.exists()
    assert written.read_text() == html
    assert 'My Vase' in html  # title from initialization_data threaded through


def test_bbox_is_embedded_for_camera_framing():
    html = fc.transform(_design(), '3d_html', _controls(), show_tips=False)
    bbox = _embedded_data(html)['bbox']
    assert bbox['range'][2] > 0  # non-zero height
    assert len(bbox['mid']) == 3
