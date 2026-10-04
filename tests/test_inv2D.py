"""
Regression test for bin/inv2D.py: run a short, seeded inversion and compare the
checksums of the results against reference values.

If a change to the code is expected to modify the results, rerun the command in
run_inv2D with the same options and update REFERENCE_CHECKSUMS.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "input" / "1st_step_2D" / "2.5s" / "data"

# obtained with seed 1234, 5000 iterations (2000 burn-in), 8 chains
REFERENCE_CHECKSUMS = {
    "inferred_vel": 5.241692717062142e+03,
    "inferred_vel_std": 1.321284165013971e+03,
    "mean_vel": 5.241692717062142e+03,
    "medi_vel": 5.166956100057533e+03,
    "std_vel": 1.224945255047224e+03,
}

OUTPUT_FILES = ["velocity_map.png", "inferred_vel.txt", "inferred_vel_std.txt",
                "mean_vel.txt", "medi_vel.txt", "std_vel.txt", "grid.txt"]


@pytest.fixture(scope="module")
def run_inv2D(tmp_path_factory):
    results_dir = tmp_path_factory.mktemp("results")
    cmd = [sys.executable, str(ROOT / "bin" / "inv2D.py"),
           f"--data={DATA}", "--target-period=2.5", f"--results-dir={results_dir}",
           "--checksum", "--seed=1234",
           "--n-iterations=5000", "--burnin-iterations=2000", "--n-chains=8"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert proc.returncode == 0, proc.stderr

    checksums = {}
    for line in proc.stdout.splitlines():
        if line.startswith("checksum "):
            _, name, value = line.split()
            checksums[name] = float(value)
    return results_dir, checksums


def test_output_files(run_inv2D):
    results_dir, _ = run_inv2D
    for name in OUTPUT_FILES:
        assert (results_dir / name).is_file(), f"{name} was not written"


@pytest.mark.parametrize("name", sorted(REFERENCE_CHECKSUMS))
def test_checksum(run_inv2D, name):
    _, checksums = run_inv2D
    assert name in checksums, f"no checksum printed for {name}"
    assert checksums[name] == pytest.approx(REFERENCE_CHECKSUMS[name], rel=1e-10)


def test_checksum_matches_saved_file(run_inv2D):
    # the printed checksum must describe what was written to disk
    results_dir, checksums = run_inv2D
    values = np.loadtxt(results_dir / "inferred_vel.txt")
    assert np.sum(np.abs(values)) == pytest.approx(checksums["inferred_vel"], rel=1e-12)
