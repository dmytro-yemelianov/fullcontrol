"""3MF Toolpath import/export (fullcontrol/ir/threemf.py) - EXPERIMENTAL interop.

The 3MF Toolpath/Laser-Toolpath extension is a draft (linear-only, sliced scan-vector); these tests
pin the structural validity of the OPC container and the documented round-trip fidelity: the
EXTRUDING XYZ path is recovered within device-unit tolerance, arcs are (lossily) tessellated to
lines, bead width/height and speed survive via the profile, and travel/procedures are dropped.
"""
import zipfile
import xml.etree.ElementTree as ET

import pytest

import fullcontrol as fc
from fullcontrol.ir import resolve, to_3mf, from_3mf
from fullcontrol.ir.toolpath import Segment, Toolpath
from fullcontrol.ir.threemf import MODEL_PATH, NS_TOOLPATH


def _controls():
    return fc.GcodeControls(printer_name='generic', initialization_data={'nozzle_temp': 210})


def _planar_design():
    'Two layers of square-ish extrusion plus a travel and a non-motion step.'
    return [
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
        fc.Point(x=20, y=0, z=0.2),
        fc.Point(x=20, y=20, z=0.2),
        fc.Point(x=0, y=20, z=0.2),
        fc.Extruder(on=False),                       # travel up to next layer
        fc.Point(x=0, y=0, z=0.4),
        fc.ManualGcode(text='; layer change'),       # a dropped pass-through step
        fc.Extruder(on=True),
        fc.Point(x=20, y=0, z=0.4),
        fc.Point(x=20, y=20, z=0.4),
    ]


def _arc_design():
    return [
        fc.ExtrusionGeometry(width=0.5, height=0.3),
        fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
        fc.Point(x=20, y=0, z=0.2),
        fc.Arc(centre=fc.Point(x=20, y=10), end=fc.Point(x=20, y=20),
               direction='anticlockwise', segments=64),
    ]


def _extruding(tp):
    return [e for e in tp.events if isinstance(e, Segment) and not e.travel]


def _total_length(segs):
    return sum(s.length for s in segs)


# ----------------------------------------------------------------------------- container validity

def test_export_is_valid_zip_with_expected_parts(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None                  # no corrupt entries
        names = z.namelist()
        assert '[Content_Types].xml' in names
        assert '_rels/.rels' in names
        assert MODEL_PATH in names                  # the model root
        assert any(n.startswith('3D/toolpath/layer_') for n in names)  # >=1 toolpath part


def test_model_root_carries_toolpathresource(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    with zipfile.ZipFile(out) as z:
        root = ET.fromstring(z.read(MODEL_PATH))
    res = root.find(f'{{{NS_TOOLPATH}}}toolpathresource')
    assert res is not None
    profiles = res.find(f'{{{NS_TOOLPATH}}}toolpathprofiles')
    layers = res.find(f'{{{NS_TOOLPATH}}}toolpathlayers')
    assert profiles is not None and len(list(profiles)) >= 1
    assert layers is not None and len(list(layers)) == 2     # two Z layers


def test_layer_parts_well_formed_xml(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    with zipfile.ZipFile(out) as z:
        layer_names = [n for n in z.namelist() if n.startswith('3D/toolpath/layer_')]
        for n in layer_names:
            ET.fromstring(z.read(n))                 # parses => well-formed


# ----------------------------------------------------------------------------------- round-trip

def test_roundtrip_recovers_extruding_xyz_within_tolerance(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))

    orig = _extruding(tp)
    got = [e for e in back.events if isinstance(e, Segment)]
    # planar straight-line design: same number of extruding line segments out
    assert len(got) == len(orig) and orig

    # point cloud (endpoints) matches within device-unit tolerance (1 micron default)
    def endpoints(segs):
        return sorted(round(c, 3) for s in segs for p in (s.start, s.end) for c in p)
    assert endpoints(got) == pytest.approx(endpoints(orig), abs=1e-3)

    # total extruding length preserved
    assert _total_length(got) == pytest.approx(_total_length(orig), abs=1e-2)


def test_roundtrip_preserves_per_layer_counts(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    # group recovered segments by their (recovered) Z; each planar layer keeps its 3 / 2 lines
    by_z = {}
    for s in back.events:
        if isinstance(s, Segment):
            by_z.setdefault(round(s.end[2], 4), 0)
            by_z[round(s.end[2], 4)] += 1
    assert set(by_z) == {0.2, 0.4}
    assert by_z[0.2] == 3 and by_z[0.4] == 2


def test_bead_width_height_survive_via_profile(tmp_path):
    tp = resolve(_planar_design(), _controls())
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    segs = [e for e in back.events if isinstance(e, Segment)]
    assert {s.width for s in segs} == {0.6}
    assert {s.height for s in segs} == {0.2}        # ExtrusionGeometry height=0.2


def test_speed_survives_via_profile(tmp_path):
    tp = resolve(_planar_design(), _controls())
    orig_speed = {s.speed for s in _extruding(tp)}
    out = tmp_path / 'design.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    got_speed = {s.speed for s in back.events if isinstance(s, Segment)}
    assert got_speed == orig_speed


def test_distinct_bead_profiles_roundtrip(tmp_path):
    'Two different (width,height) sections -> two profiles -> both recovered per-segment.'
    steps = [
        fc.ExtrusionGeometry(width=0.6, height=0.2),
        fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
        fc.Point(x=10, y=0, z=0.2),
        fc.ExtrusionGeometry(width=0.8, height=0.2),
        fc.Point(x=20, y=0, z=0.2),
    ]
    tp = resolve(steps, _controls())
    out = tmp_path / 'd.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    widths = sorted({s.width for s in back.events if isinstance(s, Segment)})
    assert widths == [0.6, 0.8]


# --------------------------------------------------------------------------- documented lossiness

def test_arc_is_tessellated_to_lines(tmp_path):
    'Known lossiness: a native arc becomes many straight line segments (no arc primitive in 3MF).'
    tp = resolve(_arc_design(), _controls())
    arcs_in = [s for s in tp.events if isinstance(s, Segment) and s.kind == 'arc']
    assert arcs_in                                   # the design has a native arc
    out = tmp_path / 'arc.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    segs = [e for e in back.events if isinstance(e, Segment)]
    assert all(s.kind == 'line' for s in segs)       # all lines on the way back
    assert all(s.centre is None for s in segs)       # arc centre is gone
    # but the arc *path length* is preserved (tessellated polyline ~ arc length)
    arc_len_in = sum(s.length for s in arcs_in)
    line_in = sum(s.length for s in tp.events
                  if isinstance(s, Segment) and not s.travel and s.kind == 'line')
    assert _total_length(segs) == pytest.approx(arc_len_in + line_in, rel=1e-3)


def test_travels_and_procedures_are_dropped(tmp_path):
    'Known lossiness: non-extruding travels and pass-through steps are not written.'
    tp = resolve(_planar_design(), _controls())
    assert any(isinstance(e, fc.ManualGcode) for e in tp.events)   # present in the IR
    assert any(isinstance(e, Segment) and e.travel for e in tp.events)
    out = tmp_path / 'd.3mf'
    to_3mf(tp, str(out), layer_height=0.2)
    back = from_3mf(str(out))
    assert not any(isinstance(e, fc.ManualGcode) for e in back.events)  # dropped
    assert all(not e.travel for e in back.events if isinstance(e, Segment))  # no travels


def test_empty_toolpath_roundtrips(tmp_path):
    'An IR with no extruding moves exports a valid (empty-geometry) container and reads back empty.'
    out = tmp_path / 'empty.3mf'
    to_3mf(Toolpath([]), str(out))
    assert zipfile.is_zipfile(out)
    back = from_3mf(str(out))
    assert [e for e in back.events if isinstance(e, Segment)] == []


def test_from_3mf_rejects_non_toolpath_zip(tmp_path):
    bad = tmp_path / 'bad.3mf'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('3D/3dmodel.model', '<model xmlns="http://x"/>')
    with pytest.raises(ValueError):
        from_3mf(str(bad))
