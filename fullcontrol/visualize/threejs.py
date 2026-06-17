"""Export a design to a self-contained three.js viewer page (result_type='3d_html').

Reuses the plot backend's `PlotData` (the same resolved paths + per-vertex colours the Plotly
preview uses) and serialises it into a single standalone HTML file: an interactive WebGL viewer with
orbit controls, the toolpath drawn as vertex-coloured lines (travels dimmed), a bed grid and a small
info overlay. The geometry is embedded as JSON in the page; three.js is pulled from a pinned CDN via
an importmap, so the file is a single self-contained document you can open in any browser or share.

    import fullcontrol as fc
    html = fc.transform(steps, '3d_html', fc.PlotControls(color_type='z_gradient'), show_tips=False)
    open('design.html', 'w').write(html)
"""
import json

from fullcontrol.visualize.state import State
from fullcontrol.visualize.plot_data import PlotData
from fullcontrol.visualize.controls import PlotControls
from fullcontrol.visualize.from_ir import visualize_from_ir
from fullcontrol.ir import resolve

THREE_VERSION = '0.160.0'  # pinned CDN build


def _paths_payload(plot_data: PlotData):
    'Serialise PlotData paths into compact {positions, colours, travel} records for the viewer.'
    paths = []
    for path in plot_data.paths:
        n = len(path.xvals)
        if n < 2:
            continue
        pos = []
        for x, y, z in zip(path.xvals, path.yvals, path.zvals):
            pos += [round(x, 3), round(y, 3), round(z, 3)]
        cols = []
        for rgb in path.colors:
            r, g, b = (float(c) for c in rgb)
            scale = 1 / 255 if max(r, g, b) > 1.0 else 1.0  # accept 0-1 or 0-255 colours
            cols += [round(r * scale, 4), round(g * scale, 4), round(b * scale, 4)]
        if len(cols) < n * 3:  # a path without per-vertex colours (e.g. a travel) -> leave empty
            cols = []
        paths.append({'p': pos, 'c': cols, 't': not bool(path.extruder.on)})
    return paths


def plot_data_to_html(plot_data: PlotData, title: str = 'FullControl design') -> str:
    'Build the self-contained viewer HTML for an already-resolved PlotData.'
    bb = plot_data.bounding_box
    payload = _paths_payload(plot_data)
    n_points = sum(len(p['p']) // 3 for p in payload)
    data = {
        'title': title,
        'paths': payload,
        'bbox': {'min': [bb.minx, bb.miny, bb.minz], 'max': [bb.maxx, bb.maxy, bb.maxz],
                 'mid': [bb.midx, bb.midy, bb.midz], 'range': [bb.rangex, bb.rangey, bb.rangez]},
        'n_points': n_points,
    }
    return _HTML_TEMPLATE.replace('__THREE_VERSION__', THREE_VERSION) \
                         .replace('__TITLE__', _escape(title)) \
                         .replace('__DATA__', json.dumps(data, separators=(',', ':')))


def _escape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def export_html(steps: list, plot_controls: PlotControls, show_tips: bool) -> str:
    '''Backend runner for result_type='3d_html'. Resolves the design to PlotData (user steps only,
    extruder defaulting on - matching the plot backend) and returns the viewer HTML string.'''
    plot_controls.initialize()
    if show_tips:
        from fullcontrol.visualize.tips import tips
        tips(plot_controls)
    state = State(steps, plot_controls)
    plot_data = PlotData(steps, state)
    toolpath = resolve(steps, plot_controls, include_procedures=False, initial_extruder_on=True)
    visualize_from_ir(toolpath, state, plot_data, plot_controls)
    # PlotControls rejects unknown fields, so the viewer's `title` / `save_as` come through its
    # initialization_data escape hatch (e.g. PlotControls(initialization_data={'save_as':'design'}))
    init = getattr(plot_controls, 'initialization_data', None) or {}
    html = plot_data_to_html(plot_data, title=init.get('title') or 'FullControl design')
    save_as = init.get('save_as')
    if save_as:
        filename = save_as if save_as.endswith('.html') else save_as + '.html'
        with open(filename, 'w') as f:
            f.write(html)
    return html


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;background:#0e0e12;overflow:hidden;font-family:system-ui,sans-serif}
  #info{position:fixed;top:12px;left:14px;color:#cfd2dc;font-size:13px;line-height:1.5;
        text-shadow:0 1px 2px #000;pointer-events:none}
  #info b{color:#fff}
  #hint{position:fixed;bottom:10px;left:14px;color:#7b8194;font-size:12px}
</style>
</head>
<body>
<div id="info"></div>
<div id="hint">drag to orbit &middot; scroll to zoom &middot; right-drag to pan</div>
<script type="importmap">
{"imports":{
  "three":"https://unpkg.com/three@__THREE_VERSION__/build/three.module.js",
  "three/addons/":"https://unpkg.com/three@__THREE_VERSION__/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const DATA = __DATA__;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0e0e12);

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth/window.innerHeight, 0.1, 100000);
camera.up.set(0,0,1);  // FullControl is Z-up

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const [cx,cy,cz] = DATA.bbox.mid;
const [rx,ry,rz] = DATA.bbox.range;
const size = Math.max(rx,ry,rz,1);
controls.target.set(cx,cy,cz);
camera.position.set(cx + size*0.9, cy - size*1.4, cz + size*0.9);

// bed grid in the XY plane (z = bed)
const grid = new THREE.GridHelper(Math.ceil(size*2), 20, 0x33384a, 0x222533);
grid.rotation.x = Math.PI/2;
grid.position.set(cx, cy, DATA.bbox.min[2]);
scene.add(grid);

const root = new THREE.Group();
for (const path of DATA.paths){
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(path.p, 3));
  let mat;
  if (path.t){                                   // travel move: faint, no vertex colours
    mat = new THREE.LineBasicMaterial({color:0x55607a, transparent:true, opacity:0.35});
  } else if (path.c && path.c.length === path.p.length){
    geom.setAttribute('color', new THREE.Float32BufferAttribute(path.c, 3));
    mat = new THREE.LineBasicMaterial({vertexColors:true});
  } else {
    mat = new THREE.LineBasicMaterial({color:0x49b0ff});
  }
  root.add(new THREE.Line(geom, mat));
}
scene.add(root);

document.getElementById('info').innerHTML =
  `<b>${DATA.title}</b><br>${DATA.n_points.toLocaleString()} points &middot; ${DATA.paths.length} paths`
  + `<br>${rx.toFixed(1)} &times; ${ry.toFixed(1)} &times; ${rz.toFixed(1)} mm`;

addEventListener('resize', ()=>{
  camera.aspect = window.innerWidth/window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

(function animate(){
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();
</script>
</body>
</html>
"""
