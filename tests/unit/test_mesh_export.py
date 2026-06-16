"""STL export (mesh_export.MeshExporter), separated from tube_mesh generation."""
import struct

from fullcontrol.visualize.tube_mesh import TubeMesh
from fullcontrol.visualize.mesh_export import MeshExporter


def _mesh():
    path = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [2, 1, 0]]
    return TubeMesh(path, 0.4, 0.4, sides=4, rounding_strength=1,
                    flat_sides=True, capped=True, inplace_path=False)


def test_binary_stl_layout_and_count(tmp_path):
    tm = _mesh()
    p = tmp_path / 'm.stl'
    tm.to_stl(str(p), binary=True, overwrite=True)
    data = p.read_bytes()
    n = struct.unpack('<I', data[80:84])[0]            # 80-byte header, then uint32 triangle count
    assert n == len(tm.triangles)
    assert len(data) == 84 + 50 * n                    # 50 bytes per triangle
    assert b'FullControlXYZ' in data[:80]


def test_ascii_stl_well_formed(tmp_path):
    tm = _mesh()
    p = tmp_path / 'm_ascii.stl'
    tm.to_stl(str(p), binary=False, overwrite=True)
    text = p.read_text()
    assert text.startswith(f'solid {p.stem}')            # solid name is the file stem
    assert text.strip().endswith(f'endsolid {p.stem}')
    assert text.count('facet normal') == len(tm.triangles)


def test_valid_path_avoids_clobbering_existing_file(tmp_path):
    existing = tmp_path / 'x.stl'
    existing.write_text('x')
    assert MeshExporter.valid_path(existing, overwrite=False) != existing  # timestamped
    assert MeshExporter.valid_path(existing, overwrite=True) == existing


def test_mesh_export_reexported_from_tube_mesh():
    from fullcontrol.visualize.tube_mesh import MeshExporter as ReExported
    assert ReExported is MeshExporter
