# slurm

Same workflow as [`../simple`](../simple), extended so that each of the 10
independent `run_task` jobs (and the final `sum_times` job) is submitted as
its own SLURM job, using Snakemake's `slurm` executor plugin.

## Layout

- `inputs/task_1.txt` .. `inputs/task_10.txt` — one input file per task, each
  containing a line `sleep=X` where `X` is a random integer between 1 and 10.
- `Snakefile` — same two rules as the `simple` example (`run_task`,
  `sum_times`), but each rule now declares SLURM `resources` (partition,
  memory, runtime, cpus) so Snakemake can submit it via `sbatch`.
- `profile/config.yaml` — a Snakemake
  [workflow profile](https://snakemake.readthedocs.io/en/stable/executing/cli.html#profiles)
  that selects the `slurm` executor and sets defaults for the SLURM account,
  partition, and per-job resources.

## Requirements (Mahuika)

Snakemake and the SLURM executor plugin are provided by the module system —
no `pip install` needed:

```bash
module load snakemake
```

## One-time setup

Edit `profile/config.yaml` and replace `<your_nesi_account>` with your NeSI
project/account code (the same one you pass to `sbatch --account` /
`salloc --account`):

```yaml
default-resources:
  slurm_account: "your_project_code"
  ...
```

Alternatively, leave the file as-is and override the account on the command
line for every run (see below).

## Running the workflow

From this directory, on a Mahuika login node:

```bash
cd slurm
module load snakemake
snakemake --profile profile
```

This submits up to 10 `run_task` SLURM jobs concurrently (one per input
file), and once all 10 have finished, submits the `sum_times` job which
aggregates their elapsed times.

If you didn't edit `profile/config.yaml`, supply the account inline instead:

```bash
snakemake --profile profile --set-resources slurm_account=your_project_code
```

To do a dry run first (no jobs submitted):

```bash
snakemake --profile profile -n
```

### Without a profile

You can also pass everything on the command line instead of using
`profile/config.yaml`:

```bash
snakemake --executor slurm --jobs 10 \
    --default-resources slurm_account=your_project_code slurm_partition=milan mem_mb=512 runtime=5
```

## Monitoring jobs

```bash
squeue --me
sacct -X --format=JobID,JobName,Partition,State,Elapsed
```

Snakemake writes SLURM stdout/stderr logs under `.snakemake/slurm_logs/`.

## Output

- `results/task_{1..10}.time` — measured elapsed time (seconds) for each task.
- `results/total_time.txt` — sum of all 10 task times.

## Cleaning up

```bash
rm -rf results .snakemake
```
