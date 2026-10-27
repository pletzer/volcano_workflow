# volcano_workflow

[![CI](https://github.com/pletzer/volcano_workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/pletzer/volcano_workflow/actions/workflows/ci.yml)

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
The chains of `inv2D.py` run in batches of `--chains-per-batch` (default 4), batch `b` being
seeded with `seed + b`. `--batches` runs only the given batches and `--partial` writes each batch
to `batch_<b>.npz` instead of the velocity maps; `merge2D.py --batches batch_*.npz` then combines
them into the same results as a single run of all the batches. The workflow uses this to run the
batches in parallel.
`inv2D.py` takes `--cell-size` to set the grid resolution in degrees (default 0.05), and
`inv1D.py` takes `--periods` to give the periods of the values in `disp.disp` (default 2 to 25 s
in steps of 0.5 s).

## Testing the scripts

```bash
python -m pytest tests
```

`tests/test_inv2D.py` and `tests/test_inv1D.py` run short, seeded inversions with `bin/inv2D.py`
and `bin/inv1D.py` and check the printed checksums against reference values in the test files. If
a change is expected to modify the results, update the reference values there.
`tests/test_inv2D.py` also checks that running the batches separately and merging them with
`bin/merge2D.py` gives the same results.
`tests/test_make_grid.py` checks `bin/make_grid.py` on small synthetic data.

## Running the workflow

The workflow in `main.nf` chains the scripts with [Nextflow](https://www.nextflow.io/):

1. `INV2D` runs `inv2D.py` for each period in `input/1st_step_2D/<period>s/data/` and each
   batch of `inv2d_chains_per_task` of the `inv2d_n_chains` Markov chains, all in parallel,
2. `MERGE2D` runs `merge2D.py` to combine the batches of each period into its 2D velocity maps,
3. `MAKE_GRID` runs `make_grid.py` to gather the 2D results into one dispersion curve per grid
   point,
4. `INV1D` runs `inv1D.py` on blocks of up to `inv1d_block_lons` x `inv1d_block_lats` grid
   points, inverting `inv1d_parallel_points` points of a block at the same time.

The parameters and profiles are defined in `nextflow.config`. Each task activates `venv/` itself, so only Nextflow needs to be loaded to use `nextflow run`.
When running on Mahuika, use `-profile mahuika` to ensure that the correct Python module is loaded for each task.

### Quick test run

The `test` profile runs the whole workflow on the current node with 2 periods (2.5 and 5.0 s), a
coarse 0.3 degree grid (56 grid points) and short Markov chains. It takes about 6 minutes using
4 cores:

```bash
module load Nextflow/26.04.0
nextflow run main.nf -profile test,mahuika
```

The results are written to `output/`:

- `output/2D/<period>s/`: the 2D velocity maps of each period,
- `output/1D/<lon>-<lat>/`: the dispersion curve (`disp.disp`) and 1D inversion results of each
  grid point.

The intermediate files of each task are kept in `workdir/`. Add `-resume` to rerun only the tasks
whose inputs or parameters have changed. Any parameter can be overridden on the command line,
e.g.

```bash
nextflow run main.nf -profile test,mahuika -resume --periods=2.5 --cell_size=0.25
```

Delete `workdir/`, `output/` and `.nextflow*` to start from scratch.

### Input, output and work directories

By default, the workflow reads the data from `input/1st_step_2D/` in this repository and writes
`output/` and `workdir/` in the directory where `nextflow` is launched. To use other directories:

```bash
nextflow run main.nf -profile test \
    --input=/path/to/1st_step_2D \
    --outdir=/path/to/output \
    -w /path/to/workdir
```

- `--input`: directory containing one `<period>s/data/` subdirectory per period,
- `--outdir`: directory where the results are published,
- `-w` (one dash, a Nextflow option): directory where the tasks run and keep their intermediate
  files. Use the same `-w` with `-resume`, since the cached tasks are looked up there. On Mahuika,
  put it on `/nesi/nobackup`.

Relative paths are resolved from the directory where `nextflow` is launched.

## How to add tomo_mpi

Currently, the workflow does not run the `tomo_mpi` step. However, it can be added by following these steps:

1. Write the process. Add this section in `main.nf`.
```
process TOMO2D {
    tag "${period}s"
    publishDir "${params.outdir}/2D_tomo", mode: 'copy'

    input:
    tuple val(period), path(data)

    output:
    tuple val(period), path("${period}s/*")

    script:
    def seed = params.seed != null ? "-S ${params.seed}" : ''
    """
    mkdir -p ${period}s
    mpiexec -n ${task.cpus} tomo_mpi  \\
        -s ${data}/sources.dat -r ${data}/receivers.dat \\
        -o ${data}/observed_t.dat -R ${data}/pathfile.dat \\
        -p ${period}s/ -b ${params.tomo_burnin} -t ${params.tomo_total} ${seed}
    tomo2grid.py --results-dir=${period}s
    """
}
```
2. Create a workflow entry. In `main.nf`, add the line
```
   TOMO2D(input)
```
below the line
```
def results_2d = INV2D(inputs).map { period, files -> tuple(period, [files].flatten()[0].parent) }
```

### Running on Mahuika with Slurm

The `slurm` profile submits each task as its own Slurm job, with the resources set in
`nextflow.config` (`inv2d_memory`, `inv2d_time`, `inv1d_memory`, `inv1d_time`; `INV1D` requests one
core per chain unless `--seed` is given). Tasks killed for running out of memory or time are
resubmitted up to twice, with the memory and time multiplied by the attempt number.

The Nextflow head process must keep running until all the tasks have completed, so run it as a
Slurm job too, from the top directory of this repository:

```bash
sbatch --account=<project> submit_mahuika.sl --account=<project>
```

The first `--account` is for the head job, the second (passed to Nextflow) for the task jobs; leave
them out to use your default Slurm account. Arguments after `submit_mahuika.sl` are passed to
`nextflow run`, e.g. `--outdir=...` or `-w ...`. The head job runs with `-resume`, so if it runs
out of time, submit it again to continue where it stopped. The log of the head job is written to
`slurm-<jobid>.out`.

For a quick check of the Slurm setup, combine the `mahuika` and `slurm` profiles with the `test` profile (about
5 minutes):

```bash
PROFILE=test,mahuika,slurm sbatch --account=<project> --time=01:00:00 submit_mahuika.sl --account=<project>
```

### Workflow diagram

To draw the graph of the processes without running them:

```bash
nextflow run main.nf -profile test -preview -with-dag dag.html
```

The format follows the extension: `.html` and `.mmd` (Mermaid), or `.png`, `.svg` and `.pdf`, which
require Graphviz (`dot`).
