"""
Regression test for bin/1D_inv.py: run a short, seeded inversion and compare the
checksums of the results against reference values.

If a change to the code is expected to modify the results, rerun the command in
run_1D_inv with the same options and update REFERENCE_CHECKSUMS.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "input" / "2nd_step_1D" / "174.0315--35.6804"

# obtained with seed 1234, 2000 iterations (500 burn-in), 4 chains
REFERENCE_CHECKSUMS = {
    "mean": 5.511238034535111e+02,
    "medi": 5.365179957407036e+02,
}

OUTPUT_FILES = ["fig1.pdf", "fig2.pdf", "mean.txt", "medi.txt", "dpth.txt"]


@pytest.fixture(scope="module")
def run_1D_inv(tmp_path_factory):
    results_dir = tmp_path_factory.mktemp("results")
    cmd = [sys.executable, str(ROOT / "bin" / "1D_inv.py"),
           f"--data={DATA}", f"--results-dir={results_dir}",
           "--checksum", "--seed=1234",
           "--n-iterations=2000", "--burnin-iterations=500", "--n-chains=4"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert proc.returncode == 0, proc.stderr

    checksums = {}
    for line in proc.stdout.splitlines():
        if line.startswith("checksum "):
            _, name, value = line.split()
            checksums[name] = float(value)
    return results_dir, checksums


def test_output_files(run_1D_inv):
    results_dir, _ = run_1D_inv
    for name in OUTPUT_FILES:
        assert (results_dir / name).is_file(), f"{name} was not written"


@pytest.mark.parametrize("name", sorted(REFERENCE_CHECKSUMS))
def test_checksum(run_1D_inv, name):
    _, checksums = run_1D_inv
    assert name in checksums, f"no checksum printed for {name}"
    assert checksums[name] == pytest.approx(REFERENCE_CHECKSUMS[name], rel=1e-10)


def test_checksum_matches_saved_file(run_1D_inv):
    # the printed checksum must describe what was written to disk
    results_dir, checksums = run_1D_inv
    values = np.loadtxt(results_dir / "mean.txt")
    assert np.sum(np.abs(values)) == pytest.approx(checksums["mean"], rel=1e-12)
