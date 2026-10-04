# Examples of Snakemake workflows

## Setup on Mahuika

```
module load snakemake/9.16.3-foss-2023a
```

## simple

Tasks are executed in parallel. A final task combines the results.

```
snakemake
```

## slurm 

As above, but the tasks are submitted via SLURM.
