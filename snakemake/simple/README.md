# simple

A minimal Snakemake workflow demonstrating parallel execution of independent
jobs followed by an aggregation step.

## Layout

- `inputs/task_1.txt` .. `inputs/task_10.txt` — one input file per task, each
  containing a line `sleep=X` where `X` is a random integer between 1 and 10.
- `Snakefile` — defines:
  - `run_task`: reads the `sleep=X` value from an input file, sleeps for `X`
    seconds, and writes the measured elapsed time to `results/task_{i}.time`.
    The 10 `run_task` jobs have no dependencies on each other, so Snakemake
    can schedule them concurrently.
  - `sum_times`: waits for all 10 `results/task_{i}.time` files and writes
    their sum to `results/total_time.txt`.

## Requirements

```bash
pip install snakemake
```

## Running the workflow

From this directory:

```bash
cd simple
snakemake --cores 10
```

`--cores 10` allows all 10 independent `run_task` jobs to run in parallel
(one per core); `sum_times` will only start once all 10 have finished.

To see the execution plan without running anything:

```bash
snakemake --cores 10 -n
```

To visualize the job graph:

```bash
snakemake --dag | dot -Tpng > dag.png
```

## Output

- `results/task_{1..10}.time` — measured elapsed time (seconds) for each task.
- `results/total_time.txt` — sum of all 10 task times.

## Cleaning up

```bash
snakemake --cores 1 --delete-all-output
# or simply
rm -rf results
```
