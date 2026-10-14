"""
Unit test for bin/make_grid.py: gather synthetic inv2D.py results of several
periods and check the dispersion curve written for each grid point.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]

PERIODS = [2.0, 2.5, 3.0]
GRID = np.array([[174.0315, -35.6804],
                 [174.0815, -35.6804],
                 [174.0315, -35.7304]])


def velocity(period):
    # a different, known velocity at each grid point and period
    return period + 0.1*np.arange(GRID.shape[0])


def write_results(path, period, grid=GRID):
    path.mkdir(parents=True)
    np.savetxt(path / "grid.txt", grid)
    np.savetxt(path / "inferred_vel.txt", velocity(period))
    return path


def run_make_grid(data, periods, results_dir):
    cmd = [sys.executable, str(ROOT / "bin" / "make_grid.py"),
           "--data", *map(str, data), "--periods", *map(str, periods),
           f"--results-dir={results_dir}"]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=60)


@pytest.fixture
def data_dirs(tmp_path):
    return [write_results(tmp_path / f"{p}s" / "results", p) for p in PERIODS]


def test_dispersion_curves(data_dirs, tmp_path):
    results_dir = tmp_path / "grid"
    proc = run_make_grid(data_dirs, PERIODS, results_dir)
    assert proc.returncode == 0, proc.stderr

    names = sorted(p.name for p in results_dir.iterdir())
    assert names == sorted(["174.0315--35.6804", "174.0815--35.6804", "174.0315--35.7304"])

    for i, (lon, lat) in enumerate(GRID):
        disp = np.loadtxt(results_dir / f"{lon}-{lat}" / "disp.disp")
        expected = [velocity(p)[i] for p in PERIODS]
        np.testing.assert_allclose(disp, expected)


def test_periods_in_any_order(data_dirs, tmp_path):
    # the dispersion curves are ordered by increasing period, whatever the input order
    results_dir = tmp_path / "grid"
    proc = run_make_grid(data_dirs[::-1], PERIODS[::-1], results_dir)
    assert proc.returncode == 0, proc.stderr

    lon, lat = GRID[1]
    disp = np.loadtxt(results_dir / f"{lon}-{lat}" / "disp.disp")
    np.testing.assert_allclose(disp, [velocity(p)[1] for p in PERIODS])


def test_mismatched_number_of_periods(data_dirs, tmp_path):
    proc = run_make_grid(data_dirs, PERIODS[:-1], tmp_path / "grid")
    assert proc.returncode != 0
    assert "periods" in proc.stderr


def test_different_grids(data_dirs, tmp_path):
    other = write_results(tmp_path / "other", 3.5, grid=GRID + 0.01)
    proc = run_make_grid(data_dirs + [other], PERIODS + [3.5], tmp_path / "grid")
    assert proc.returncode != 0
    assert "grid.txt" in proc.stderr
