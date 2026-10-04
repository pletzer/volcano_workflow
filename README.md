# volcano_workflow
Examples of workflows for analysing volcano data

## Installation

The Python scripts in `bin/` require Python 3 (tested with Python 3.12). To create a virtual
environment with all the dependencies installed, run the following from the top directory of
this repository:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Activate the environment with `source venv/bin/activate` in each new shell before running the
scripts, and type `deactivate` to leave it.

Note: `seislib` builds C extensions on installation and may require a C compiler. `cartopy`
depends on the GEOS and PROJ libraries; if `pip` fails to install it, install these libraries
first (e.g. `brew install geos proj` on macOS) or use a conda environment instead.

## Usage

```bash
python bin/bayesbay2D.py --data=data --target-period=3.0 --results-dir=results
python bin/genvizfile.py --results-dir=results --output=velocity.vtr
```

Run each script with `--help` for a description of its options.
