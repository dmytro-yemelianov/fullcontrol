"""CLI tests for the g-code engine (Phase 5).

Invokes the CLI as a subprocess (``python -m fullcontrol.gcode_engine …``) so exit codes, stdout/
stderr separation and ``--json`` validity are exercised exactly as a user would hit them. Real
g-code is generated with ``fc.transform(design, 'gcode', controls)`` and written to ``tmp_path``.
"""
import json
import subprocess
import sys

import pytest

import fullcontrol as fc


def _controls():
    # prusa_i3's start procedure emits M104/M109 (hotend heat), so the result has no
    # cold-extrusion error - a genuinely clean baseline.
    return fc.GcodeControls(
        printer_name='prusa_i3',
        initialization_data={'extrusion_width': 0.4, 'extrusion_height': 0.2},
    )


def _gcode(steps=None) -> str:
    'A small, clean FullControl design rendered to g-code text.'
    if steps is None:
        steps = [
            fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
            fc.Point(x=20, y=0), fc.Point(x=20, y=20),
            fc.Point(x=0, y=20), fc.Point(x=0, y=0),
            fc.Point(x=5, y=5), fc.Point(x=15, y=5),
            fc.Point(x=15, y=15), fc.Point(x=5, y=15), fc.Point(x=5, y=5),
        ]
    return fc.transform(steps, 'gcode', _controls())


def _run(args, *, stdin=None):
    'Run the CLI subprocess; returns the CompletedProcess.'
    return subprocess.run(
        [sys.executable, '-m', 'fullcontrol.gcode_engine', *args],
        input=stdin, capture_output=True, text=True,
    )


@pytest.fixture
def clean_gcode(tmp_path):
    path = tmp_path / 'clean.gcode'
    path.write_text(_gcode())
    return path


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #

def test_verify_clean_exits_zero(clean_gcode):
    res = _run(['verify', str(clean_gcode)])
    assert res.returncode == 0, res.stderr + res.stdout
    assert 'verification' in res.stdout.lower() or 'segments' in res.stdout.lower()


def test_verify_out_of_bounds_exits_one(tmp_path):
    # a design that extrudes to a point well outside a 200x200x200 build volume -> an out-of-bounds
    # error from the reused validation rule.
    steps = [
        fc.Point(x=0, y=0, z=0.2), fc.Extruder(on=True),
        fc.Point(x=20, y=0), fc.Point(x=20, y=20), fc.Point(x=300, y=300),
    ]
    path = tmp_path / 'bad.gcode'
    path.write_text(_gcode(steps))
    res = _run(['verify', str(path), '--build-volume', '200,200,200'])
    assert res.returncode == 1, f'expected exit 1, got {res.returncode}\n{res.stdout}\n{res.stderr}'
    assert 'error' in res.stdout.lower()
    assert 'build volume' in res.stdout.lower()


def test_verify_json_is_valid(clean_gcode):
    res = _run(['verify', str(clean_gcode), '--json'])
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    assert set(['ok', 'issues', 'counts', 'parse_params', 'simulation']).issubset(data.keys())
    assert isinstance(data['issues'], list)
    assert data['simulation'] is not None


def test_verify_reads_stdin(clean_gcode):
    res = _run(['verify', '-'], stdin=clean_gcode.read_text())
    assert res.returncode == 0, res.stderr


# --------------------------------------------------------------------------- #
# optimise
# --------------------------------------------------------------------------- #

def test_optimise_writes_output_file(clean_gcode, tmp_path):
    out = tmp_path / 'out.gcode'
    res = _run(['optimise', str(clean_gcode), '-o', str(out)])
    assert res.returncode == 0, res.stderr
    assert out.exists()
    text = out.read_text()
    assert text.strip(), 'optimised g-code file is empty'
    # the report goes to stderr when -o is used
    assert 'optimise' in res.stderr.lower()

    # the written file re-parses cleanly (no errors)
    res2 = _run(['verify', str(out)])
    assert res2.returncode == 0, res2.stdout + res2.stderr


def test_optimise_json_is_valid(clean_gcode):
    res = _run(['optimise', str(clean_gcode), '--json'])
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    assert 'segments_before' in data and 'segments_after' in data
    assert 'passes' in data and isinstance(data['passes'], list)
    assert data['output'], 'expected optimised g-code under "output" when no -o'


def test_optimise_unknown_pass_errors(clean_gcode):
    res = _run(['optimise', str(clean_gcode), '--passes', 'foo'])
    assert res.returncode != 0
    assert 'foo' in res.stderr.lower() and 'unknown' in res.stderr.lower()


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #

def test_inspect_clean(clean_gcode):
    res = _run(['inspect', str(clean_gcode)])
    assert res.returncode == 0, res.stderr
    out = res.stdout.lower()
    assert 'segments' in out
    assert 'time' in out
    assert 'material' in out


def test_inspect_json_is_valid(clean_gcode):
    res = _run(['inspect', str(clean_gcode), '--json'])
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    assert set(['parse_params', 'simulation', 'bbox', 'counts', 'ok']).issubset(data.keys())
    assert data['simulation']['segment_count'] > 0
    assert data['bbox'] is not None


# --------------------------------------------------------------------------- #
# errors / general
# --------------------------------------------------------------------------- #

def test_missing_file_no_traceback(tmp_path):
    res = _run(['verify', str(tmp_path / 'nope.gcode')])
    assert res.returncode == 2
    assert 'Traceback' not in res.stderr
    assert 'error' in res.stderr.lower()


def test_help_exits_zero():
    res = _run(['--help'])
    assert res.returncode == 0
    assert 'verify' in res.stdout and 'optimise' in res.stdout and 'inspect' in res.stdout
