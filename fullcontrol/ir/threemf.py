"""3MF Toolpath import/export for the FullControl Toolpath IR (EXPERIMENTAL / best-effort).

This module lowers the FullControl Toolpath IR into - and lifts it back from - a structurally
valid **3MF (OPC ZIP) container** whose toolpath part follows the **3MF Toolpath / Laser-Toolpath
extension draft** (namespace ``http://schemas.microsoft.com/3dmanufacturing/toolpath/2019/05``,
repo https://github.com/3MFConsortium/spec_lasertoolpath). 3MF Toolpath is the strategic
interchange / archive target identified in docs/ir_prior_art.md.

**EXPERIMENTAL.** The 3MF Toolpath/Laser-Toolpath extension is an unreleased *draft*; its OPC
packaging (content-type strings, the model<->resource relationship wiring, a fully worked example
package) is under-specified. We target the documented draft element/attribute *names* and produce a
self-contained, deterministic container, but the exact bytes are our clean approximation, not a
ratified format. Treat this as a tracking implementation, to be tightened as the spec stabilises.

What 3MF Toolpath is (and what that costs us):
  * It is a **sliced / scan-vector** model, **linear-only - there are NO arc primitives**. On export
    we tessellate every IR arc into short line segments (lossy; the native arc centre/clockwise is
    not representable). A polyline executed as a continuous mark is a ``<segment type="polyline">``
    holding a list of ``<point x= y=>`` device-unit coordinates.
  * Geometry is grouped into **layers** by Z. FullControl designs may be non-planar; we bucket
    segments by their *end* Z (rounded to ``layer_height`` if given, else by distinct Z value), so
    layering is **approximate** for non-planar paths (a single sloped move lands in one Z bucket).
  * Per-move bead geometry is carried as a **toolpath profile** with ``beadwidth`` / ``beadheight``
    (these attributes exist on ``<toolpathprofile>`` in the Laser-Toolpath schema). A distinct
    (width,height) pair => a distinct profile; each segment references its profile by id.
  * Speed (mm/min) is carried on the profile as ``depositionspeed`` (a documented profile attribute).

Parts written (the OPC ZIP layout):
  * ``[Content_Types].xml``      - OPC content-type map (model + toolpath + rels defaults).
  * ``_rels/.rels``              - package root relationship -> the 3D model part (3MF startpart).
  * ``3D/3dmodel.model``         - the core 3MF model root: a ``<model>`` with one ``<object>``/
                                   ``<build>`` (a minimal valid 3MF core document) plus a
                                   ``<tp:toolpathresource>`` carrying ``<tp:toolpathprofiles>`` and
                                   ``<tp:toolpathlayers>`` (each layer references its layer part by
                                   ``path``).
  * ``3D/_rels/3dmodel.model.rels`` - relationships from the model part to each layer part, using
                                   the draft relationship type
                                   ``http://schemas.microsoft.com/3dmanufacturing/2019/05/toolpath``.
  * ``3D/toolpath/layer_00001.xml`` (one per layer) - a ``<layer>`` (default toolpath namespace)
                                   holding ``<parts>``, ``<profiles>``, ``<data>`` and ``<segments>``
                                   with the per-layer ``<segment>``/``<point>`` geometry.

Coordinates are stored as **integer device units**; the resource ``unitfactor`` (mm per device unit,
default 1e-3 => micron resolution) converts back to mm on read, exactly per the draft.

Round-trip fidelity (``from_3mf(to_3mf(tp))``) - documented and asserted in tests:
  PRESERVED  : the EXTRUDING XYZ geometry (every extruding line's start/end within device-unit
               tolerance). X/Y come from the segment ``<point>``s; Z is recovered from the parent
               ``<toolpathlayer ztop=...>`` (so a single Z per layer - exact for planar designs,
               approximate for non-planar where a move spans Z within its bucket). Arc paths are
               preserved as their tessellated polylines, per-layer segment counts, bead width/height
               (via the profile), and speed (via the profile's depositionspeed).
  LOSSY/DROP : native arcs become straight line segments (centre/clockwise gone); travel (non-
               extruding) moves are NOT written (3MF Toolpath encodes marking geometry only);
               pass-through steps (temperature/fan/manual g-code) and StationaryExtrusion material
               events are dropped; absolute deposited_volume/filament_length are recomputed from
               geometry+bead on read (not stored), so they match only up to the IR's own area model.

Public API (exported from ``fullcontrol.ir`` and re-exported as ``fc.to_3mf`` / ``fc.from_3mf``):
    to_3mf(toolpath, path, *, layer_height=None) -> None
    from_3mf(path) -> Toolpath

Stdlib only: ``zipfile`` + ``xml.etree.ElementTree``.
"""
import hashlib
import zipfile
import xml.etree.ElementTree as ET

from fullcontrol.ir.toolpath import Toolpath, Segment

# --- namespaces / relationship types / content types (3MF core + toolpath draft) ---------------
NS_TOOLPATH = 'http://schemas.microsoft.com/3dmanufacturing/toolpath/2019/05'
NS_CORE = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
NS_CONTENT_TYPES = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
REL_STARTPART = 'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel'
REL_TOOLPATH = 'http://schemas.microsoft.com/3dmanufacturing/2019/05/toolpath'
CT_MODEL = 'application/vnd.ms-package.3dmanufacturing-3dmodel+xml'
# Draft does not pin a content-type string for layer parts; we use a clear, namespaced one.
CT_TOOLPATH_LAYER = 'application/vnd.ms-package.3dmanufacturing-toolpathlayer+xml'

MODEL_PATH = '3D/3dmodel.model'
LAYER_DIR = '3D/toolpath'

DEFAULT_UNIT_FACTOR = 1e-3   # mm per device unit (1 device unit = 1 micron)
DEFAULT_SPEED = 1000.0       # mm/min, used on import when a profile carries no depositionspeed
_Z_DECIMALS = 6              # rounding for Z bucketing when no layer_height is given


# ============================== EXPORT ==========================================================

def _tessellate(seg: Segment):
    '''The (x,y,z) polyline for a segment: arcs use their tessellated ``arc_points`` (prepended with
    the start), lines are just [start, end]. 3MF Toolpath has no arc primitive, so this is the lossy
    arc -> lines step.'''
    if seg.kind == 'arc' and seg.arc_points:
        return [tuple(seg.start), *(tuple(p) for p in seg.arc_points)]
    return [tuple(seg.start), tuple(seg.end)]


def _layer_key(z, layer_height):
    'Bucket a Z value into a layer index/key (rounded to layer_height if given, else distinct Z).'
    if z is None:
        return 0.0
    if layer_height:
        return round(z / layer_height) * layer_height
    return round(z, _Z_DECIMALS)


def _to_device(v, unit_factor):
    'mm -> integer device units (round-to-nearest); None -> 0.'
    return int(round((v or 0.0) / unit_factor))


def _profile_key(seg):
    'A (width, height, speed) triple identifying a distinct toolpath profile.'
    return (seg.width, seg.height, seg.speed)


def to_3mf(toolpath: Toolpath, path: str, *, layer_height=None) -> None:
    '''Export the IR's EXTRUDING moves to a 3MF Toolpath (OPC ZIP) container at ``path``.

    Only extruding segments are written (3MF Toolpath encodes marking geometry). Arcs are
    tessellated to line segments. Segments are grouped into ``<layer>`` parts by end-Z (rounded to
    ``layer_height`` if given). Bead width/height and speed are carried as ``<toolpathprofile>``
    attributes (``beadwidth``/``beadheight``/``depositionspeed``); each segment references its
    profile by id. See the module docstring for exactly what is preserved vs lossy.'''
    unit_factor = DEFAULT_UNIT_FACTOR
    extruding = [e for e in toolpath.events if isinstance(e, Segment) and not e.travel]

    # assign a stable profile id per distinct (width, height, speed)
    profiles = {}          # key -> profile id (1-based)
    for seg in extruding:
        profiles.setdefault(_profile_key(seg), len(profiles) + 1)

    # group segments into layers by end-Z bucket, preserving event order within a layer
    layers = {}            # layer key -> list[Segment]
    for seg in extruding:
        layers.setdefault(_layer_key(seg.end[2], layer_height), []).append(seg)
    layer_keys = sorted(layers, key=lambda k: (k is None, k))

    # --- build the per-layer parts -------------------------------------------------------------
    layer_parts = {}       # opc part name -> xml bytes
    layer_refs = []        # (opc part name, ztop_device) in order, for the resource's <toolpathlayers>
    for idx, key in enumerate(layer_keys, start=1):
        part_name = f'{LAYER_DIR}/layer_{idx:05d}.xml'
        layer_parts[part_name] = _layer_xml(layers[key], profiles, unit_factor)
        layer_refs.append((part_name, _to_device(key, unit_factor)))

    model_xml = _model_xml(profiles, layer_refs, unit_factor)

    # --- write the OPC ZIP ---------------------------------------------------------------------
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _content_types_xml())
        z.writestr('_rels/.rels', _root_rels_xml())
        z.writestr(MODEL_PATH, model_xml)
        z.writestr('3D/_rels/3dmodel.model.rels', _model_rels_xml(layer_refs))
        for part_name, data in layer_parts.items():
            z.writestr(part_name, data)


def _content_types_xml() -> bytes:
    types = ET.Element(f'{{{NS_CONTENT_TYPES}}}Types')
    ET.SubElement(types, f'{{{NS_CONTENT_TYPES}}}Default',
                  {'Extension': 'rels',
                   'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(types, f'{{{NS_CONTENT_TYPES}}}Override',
                  {'PartName': '/' + MODEL_PATH, 'ContentType': CT_MODEL})
    # layer parts share the .xml extension; declare a Default for xml -> the toolpath-layer type
    ET.SubElement(types, f'{{{NS_CONTENT_TYPES}}}Default',
                  {'Extension': 'xml', 'ContentType': CT_TOOLPATH_LAYER})
    return _serialize(types, default_ns=NS_CONTENT_TYPES)


def _root_rels_xml() -> bytes:
    rels = ET.Element(f'{{{NS_REL}}}Relationships')
    ET.SubElement(rels, f'{{{NS_REL}}}Relationship',
                  {'Id': 'rel0', 'Type': REL_STARTPART, 'Target': '/' + MODEL_PATH})
    return _serialize(rels, default_ns=NS_REL)


def _model_rels_xml(layer_refs) -> bytes:
    rels = ET.Element(f'{{{NS_REL}}}Relationships')
    for i, (part_name, _z) in enumerate(layer_refs, start=1):
        ET.SubElement(rels, f'{{{NS_REL}}}Relationship',
                      {'Id': f'rel{i}', 'Type': REL_TOOLPATH, 'Target': '/' + part_name})
    return _serialize(rels, default_ns=NS_REL)


def _model_xml(profiles, layer_refs, unit_factor) -> bytes:
    'The 3MF core <model> with a minimal build, plus the <tp:toolpathresource>.'
    model = ET.Element(f'{{{NS_CORE}}}model', {'unit': 'millimeter'})
    # minimal-but-valid core 3MF body: one (empty) object + a build that references it.
    resources = ET.SubElement(model, f'{{{NS_CORE}}}resources')
    ET.SubElement(resources, f'{{{NS_CORE}}}object', {'id': '2', 'type': 'model'})
    build = ET.SubElement(model, f'{{{NS_CORE}}}build')
    ET.SubElement(build, f'{{{NS_CORE}}}item', {'objectid': '2'})

    # the toolpath resource
    res = ET.SubElement(model, f'{{{NS_TOOLPATH}}}toolpathresource',
                        {'id': '1', 'uuid': _stable_uuid('resource'),
                         'unitfactor': repr(unit_factor), 'toolpathtype': 'planar'})
    tp_profiles = ET.SubElement(res, f'{{{NS_TOOLPATH}}}toolpathprofiles')
    for (width, height, speed), pid in profiles.items():
        attrs = {'uuid': _stable_uuid(f'profile{pid}'), 'name': f'profile{pid}'}
        if width is not None:
            attrs['beadwidth'] = repr(float(width))
        if height is not None:
            attrs['beadheight'] = repr(float(height))
        if speed is not None:
            attrs['depositionspeed'] = repr(float(speed))
        ET.SubElement(tp_profiles, f'{{{NS_TOOLPATH}}}toolpathprofile', attrs)
    tp_layers = ET.SubElement(res, f'{{{NS_TOOLPATH}}}toolpathlayers')
    for part_name, ztop in layer_refs:
        ET.SubElement(tp_layers, f'{{{NS_TOOLPATH}}}toolpathlayer',
                      {'ztop': str(ztop), 'path': '/' + part_name})
    return _serialize(model, default_ns=NS_CORE, extra_ns={'tp': NS_TOOLPATH})


def _layer_xml(segments, profiles, unit_factor) -> bytes:
    'A toolpath <layer> part: <parts>/<profiles>/<data>/<segments> with this layer\'s geometry.'
    layer = ET.Element(f'{{{NS_TOOLPATH}}}layer')
    # <parts>: one local part id (1) mapping to the (empty) build object's uuid
    parts = ET.SubElement(layer, f'{{{NS_TOOLPATH}}}parts')
    ET.SubElement(parts, f'{{{NS_TOOLPATH}}}part', {'id': '1', 'uuid': _stable_uuid('part1')})
    # <profiles>: local profile id -> resource profile uuid, only for profiles used in this layer
    used = []
    seen = set()
    for seg in segments:
        pid = profiles[_profile_key(seg)]
        if pid not in seen:
            seen.add(pid)
            used.append(pid)
    profs = ET.SubElement(layer, f'{{{NS_TOOLPATH}}}profiles')
    for pid in used:
        ET.SubElement(profs, f'{{{NS_TOOLPATH}}}profile',
                      {'id': str(pid), 'uuid': _stable_uuid(f'profile{pid}')})
    ET.SubElement(layer, f'{{{NS_TOOLPATH}}}data')
    segs_el = ET.SubElement(layer, f'{{{NS_TOOLPATH}}}segments')
    for seg in segments:
        pid = profiles[_profile_key(seg)]
        s_el = ET.SubElement(segs_el, f'{{{NS_TOOLPATH}}}segment',
                             {'type': 'polyline', 'profileid': str(pid), 'partid': '1'})
        for (x, y, _z) in _tessellate(seg):
            ET.SubElement(s_el, f'{{{NS_TOOLPATH}}}point',
                          {'x': str(_to_device(x, unit_factor)), 'y': str(_to_device(y, unit_factor))})
    return _serialize(layer, default_ns=NS_TOOLPATH)


def _stable_uuid(seed: str) -> str:
    'A deterministic UUID-shaped string (the draft requires uuid attributes; values are arbitrary).'
    h = hashlib.sha1(seed.encode()).hexdigest()
    return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'


def _serialize(root, *, default_ns, extra_ns=None) -> bytes:
    '''Serialize an ElementTree built with Clark-notation ({ns}tag) names into namespaced XML.
    Registers ``default_ns`` as the empty prefix so the output uses unqualified element names where
    possible (the draft uses ``elementFormDefault`` unqualified for layer content).'''
    ET.register_namespace('', default_ns)
    if extra_ns:
        for prefix, uri in extra_ns.items():
            ET.register_namespace(prefix, uri)
    body = ET.tostring(root, encoding='unicode')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body).encode('utf-8')


# ============================== IMPORT ==========================================================

def _localname(tag: str) -> str:
    'Strip any {namespace} from a Clark-notation tag.'
    return tag.rsplit('}', 1)[-1]


def _find(parent, name):
    'First child whose local name matches `name` (namespace-agnostic), else None.'
    for child in parent:
        if _localname(child.tag) == name:
            return child
    return None


def _findall(parent, name):
    'All descendants (any depth) whose local name matches `name` (namespace-agnostic).'
    return [el for el in parent.iter() if _localname(el.tag) == name]


def from_3mf(path: str) -> Toolpath:
    '''Import a 3MF Toolpath container into a Toolpath IR of straight-line extruding Segments.

    Reads the OPC ZIP, parses the model root for the ``<tp:toolpathresource>`` (unitfactor +
    profiles) and its layer references, then parses each ``<layer>`` part's ``<segment>``/``<point>``
    geometry back into IR Segments. Each polyline point pair becomes one line Segment; width/height
    come from the referenced profile's ``beadwidth``/``beadheight`` (None if absent); speed from
    ``depositionspeed`` (else ``DEFAULT_SPEED``). All imported segments are extruding (``travel=
    False``); deposited_volume/filament_length are recomputed from length*area (height*width). See
    the module docstring for what this does and does not recover.'''
    with zipfile.ZipFile(path, 'r') as z:
        model_root = ET.fromstring(z.read(MODEL_PATH))
        resource = _find(model_root, 'toolpathresource')
        if resource is None:
            raise ValueError(f'{path}: no <toolpathresource> in {MODEL_PATH} (not a 3MF Toolpath file?)')
        unit_factor = float(resource.get('unitfactor', DEFAULT_UNIT_FACTOR))

        # profile id (1-based, in document order) -> (width, height, speed)
        profile_attrs = {}
        tp_profiles = _find(resource, 'toolpathprofiles')
        if tp_profiles is not None:
            for i, prof in enumerate(_findall(tp_profiles, 'toolpathprofile'), start=1):
                profile_attrs[i] = (
                    _opt_float(prof.get('beadwidth')),
                    _opt_float(prof.get('beadheight')),
                    _opt_float(prof.get('depositionspeed')))
        # also key by the resource-profile uuid so a layer's local id->uuid map can resolve it
        uuid_attrs = {}
        if tp_profiles is not None:
            for prof in _findall(tp_profiles, 'toolpathprofile'):
                uuid_attrs[prof.get('uuid')] = (
                    _opt_float(prof.get('beadwidth')),
                    _opt_float(prof.get('beadheight')),
                    _opt_float(prof.get('depositionspeed')))

        tp_layers = _find(resource, 'toolpathlayers')
        layer_paths = []   # (opc part name, layer Z in mm or None)
        if tp_layers is not None:
            for layer_ref in _findall(tp_layers, 'toolpathlayer'):
                p = (layer_ref.get('path') or '').lstrip('/')
                ztop = layer_ref.get('ztop')
                z_mm = None if ztop is None else int(ztop) * unit_factor
                if p:
                    layer_paths.append((p, z_mm))

        events = []
        src = 0
        for layer_path, z_mm in layer_paths:
            try:
                layer_root = ET.fromstring(z.read(layer_path))
            except KeyError:
                continue
            # local profile id -> attrs, via the layer's <profiles> id->uuid map
            local_profiles = {}
            profs_el = _find(layer_root, 'profiles')
            if profs_el is not None:
                for prof in _findall(profs_el, 'profile'):
                    lid = prof.get('id')
                    attrs = uuid_attrs.get(prof.get('uuid'))
                    if lid is not None and attrs is not None:
                        local_profiles[lid] = attrs
            segs_el = _find(layer_root, 'segments')
            if segs_el is None:
                continue
            for seg_el in _findall(segs_el, 'segment'):
                width, height, speed = local_profiles.get(
                    seg_el.get('profileid'), profile_attrs.get(_safe_int(seg_el.get('profileid')),
                                                               (None, None, None)))
                pts = [(int(p.get('x')) * unit_factor, int(p.get('y')) * unit_factor)
                       for p in _findall(seg_el, 'point')]
                # planar layers carry Z on the <toolpathlayer ztop=...>; geometry stores X/Y only
                events.extend(_segments_from_points(pts, z_mm, width, height, speed, src))
                src += 1
    return Toolpath(events)


def _segments_from_points(pts, z_mm, width, height, speed, src):
    'Consecutive point pairs -> line Segments (extruding).'
    out = []
    spd = speed if speed is not None else DEFAULT_SPEED
    area = (width * height) if (width is not None and height is not None) else 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        start = (x0, y0, z_mm)
        end = (x1, y1, z_mm)
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        vol = length * area
        out.append(Segment(start=start, end=end, travel=False, speed=spd, length=length,
                           deposited_volume=vol, filament_length=0.0, source_index=src,
                           kind='line', width=width, height=height))
    return out


def _opt_float(v):
    return None if v is None else float(v)


def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
