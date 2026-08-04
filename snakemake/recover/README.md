# recover

Extends [`../slurm`](../slurm): the same 10 parallel tasks are submitted as
SLURM jobs, but each task is deliberately given a very short walltime on its
first submission. Tasks whose `sleep=X` duration exceeds the current
attempt's time limit get killed by SLURM for exceeding `--time`; Snakemake
detects the failed job and **automatically resubmits it with a larger
runtime**, up to 3 total attempts per task.

## How the recovery works

Snakemake has built-in support for this pattern via the `retries` rule
directive together with the `attempt` wildcard, which can be referenced from
`resources`:

```python
rule run_task:
    retries: 2                                    # up to 2 resubmissions (3 attempts total)
    resources:
        runtime=lambda wildcards, attempt: attempt,       # 1 min, then 2 min, then 3 min
        mem_mb=lambda wildcards, attempt: 512 * attempt,  # 512, then 1024, then 1536 MB
    run:
        ...
```

No custom retry code is needed. On each submission:

1. Snakemake submits the job via `sbatch` with the walltime and memory for
   the current `attempt` (1 minute / 512 MB on attempt 1, 2 minutes / 1024 MB
   on attempt 2, 3 minutes / 1536 MB on attempt 3).
2. If the task's `sleep=X` value is longer than the walltime, SLURM kills the
   job for hitting the time limit (state `TIMEOUT`/`CANCELLED`).
3. Snakemake sees the job did not complete successfully. Because `retries: 2`
   is set on the rule, it resubmits the same job with `attempt` incremented,
   which recomputes `runtime` (and `mem_mb`) to larger values.
4. This repeats until the job succeeds or `retries` is exhausted (3 failed
   attempts), in which case Snakemake reports the job — and the whole
   workflow — as failed.

Note that Snakemake's `retries` only know that a job failed, not *why* --
`attempt` is incremented the same way whether SLURM killed the job for
`TIMEOUT`, `OUT_OF_MEMORY`, or something else entirely. This example only
demonstrates the timeout case (`sleep=X` vs. `runtime`), but `mem_mb` is
grown on every retry too, defensively, in case a real job actually needed
more memory rather than more time. To see which one actually happened for a
given job, check `sacct` or `seff` (see "Monitoring jobs" below) rather than
relying on the workflow to tell you.

The input `sleep=X` values in `inputs/` are deliberately spread across three
ranges so you should see all three behaviours in one run:

- `X <= 60`: succeeds on attempt 1 (1 minute limit).
- `60 < X <= 120`: fails attempt 1, succeeds on attempt 2 (2 minute limit).
- `120 < X <= 170`: fails attempts 1 and 2, succeeds on attempt 3 (3 minute
  limit).

Every task's `sleep=X` is kept below 180s (the attempt-3 limit), so every
task is expected to eventually succeed within the 3 allowed attempts.

## Requirements (Mahuika)

`module load snakemake` on its own may resolve to an older, pre-8.0 release
that doesn't support the executor-plugin architecture this profile uses
(`executor: slurm`) -- see [`../slurm`](../slurm)'s README for details. Load
the versioned module instead:

```bash
module load snakemake/9.16.3
```

## Running the workflow

From this directory:

```bash
cd recover
module load snakemake/9.16.3
snakemake --profile profile
```

Because some tasks are expected to fail and resubmit, this run will take
longer than the `slurm` example and Snakemake's log will show lines like:

```
Trying to restart job ... (attempt 2 out of 3)
```

To watch resubmissions happen live, run in the foreground and keep an eye on
`squeue`/`sacct` in another terminal (see below).

### Overriding the number of attempts or the account

```bash
snakemake --profile profile --retries 4
snakemake --profile profile --set-resources slurm_account=your_project_code
```

(`--retries` overrides the default max-retries for rules that don't set
their own `retries:`; it will not reduce `run_task`'s explicit `retries: 2`
below 2. To change `run_task` itself, edit `MAX_RETRIES` in the `Snakefile`.)

### Dry run

```bash
snakemake --profile profile -n
```

Note: a dry run always shows `attempt=1` resources for every job, since
Snakemake only knows the real attempt count once a job has actually failed
and is being retried.

## Monitoring jobs

```bash
squeue --me
sacct -X --format=JobID,JobName,Partition,State,Elapsed,Timelimit,MaxRSS,ReqMem
seff <jobid>
```

Look for `State=TIMEOUT` or `CANCELLED` entries followed by a new job ID for
the same task — that's a resubmission with a larger `runtime`. A
`State=OUT_OF_MEMORY` entry instead means the job was actually killed for
running out of memory, not time; `MaxRSS` close to or above `ReqMem` (or
`seff`'s "Memory Utilized" close to 100%) confirms it.

## Output

- `results/task_{1..10}.time` — measured elapsed time (seconds) for each
  task, from whichever attempt finally succeeded.
- `results/total_time.txt` — sum of all 10 task times.

## Cleaning up

```bash
rm -rf results .snakemake
```
