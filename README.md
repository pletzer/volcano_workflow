# volcano_workflow
Examples of workflows for analysing volcano data

## Installation

The Python scripts in `bin/` require Python 3 (tested with Python 3.12 and 3.14). To create a virtual
environment with all the dependencies installed, run the following from the top directory of
this repository:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Environment

Activate the environment with `source venv/bin/activate` in each new shell before running the
scripts, and type `deactivate` to leave it.

On Mahuika, load the Python module first, both when creating the virtual environment and in
each new shell before activating it. The virtual environment is linked against the module's
Python library, so `python` fails with `error while loading shared libraries:
libpython3.14.so.1.0` if the module is not loaded:

```bash
module load Python/3.14.4-foss-2026
source venv/bin/activate
```

Note: `seislib` builds C extensions on installation and may require a C compiler. `cartopy`
depends on the GEOS and PROJ libraries; if `pip` fails to install it, install these libraries
first (e.g. `brew install geos proj` on macOS) or use a conda environment instead.

## Script usage

```bash
python bin/inv2D.py --data=input/1st_step_2D/2.5s/data --target-period=2.5 --results-dir=results
python bin/genvizfile.py --results-dir=results --output=velocity.vtm
```

`genvizfile.py` writes a VTK multiblock file `velocity.vtm` with two blocks: `velocity` (the
velocity fields on a rectilinear grid) and `coastline` (the coastline clipped to the same domain).
The blocks themselves are stored in the `velocity/` directory, which must be kept next to
`velocity.vtm`. Open `velocity.vtm` in ParaView. The coastline data are downloaded from Natural
Earth by `cartopy` on first use.

Run each script with `--help` for a description of its options.

`inv2D.py` also accepts `--seed=<int>` for reproducible runs, `--checksum` to print checksums of
the results, and `--n-iterations`, `--burnin-iterations` and `--n-chains` to change the length
of the Markov chain Monte Carlo run.

## Testing the scripts

```bash
python -m pytest tests
```

`tests/test_inv2D.py` and `tests/test_inv1D.py` run short, seeded inversions with `bin/inv2D.py`
and `bin/inv1D.py` and check the printed checksums against reference values in the test files. If
a change is expected to modify the results, update the reference values there.
`tests/test_make_grid.py` checks `bin/make_grid.py` on small synthetic data.
