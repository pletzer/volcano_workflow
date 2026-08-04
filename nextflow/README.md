# Nextflow

Nextflow uses a Domain Specific Language (DSL) to wrap around scripts and software and connect them into a pipeline.
Individual steps typically use containers or conda environments for portability, and can take on essentially any form.
Some features of Nextflow pipelines:

- ability to resume pipelines with errors and only run tasks which were not completed successfully or changed in some way
- ability to apply filtering/branching/scatter-gather/etc logic to tasks depending on the results of steps within the pipeline
- built-in reporting mechanisms

## The demos

The scripts here use a [publicly available demo pipeline for Nextflow](https://github.com/nf-core/demo/tree/1.2.0) which can be pulled automatically by Nextflow.
This pipeline processes two input files through the `fastqc` and `seqtk` processing steps, then combines the information about each file in the `multiqc` step, and separately runs the `cowpy` process.

![demo pipeline metro map](https://raw.githubusercontent.com/nf-core/demo/1.2.0/docs/images/nf-core-demo-subway.png)

There are two approaches to running the pipeline on Mahuika taken here:

1. Running all processes in the pipeline within a single job (`demo-local.sl`)
2. Running a head job which then submits new jobs for each process in the pipeline (`demo-head.sl`)

For more information on different approaches to running Nextflow on an HPC cluster, [see our documentation](https://docs.nesi.org.nz/Software/Available_Applications/Nextflow/#methods-for-running-nextflow-with-reannz).

## Nextflow SLURM integration

Nextflow can create and monitor jobs via SLURM to ensure that processes complete and all prerequisites are met before proceeding with a next step in a pipeline.
Important aspects of integrating Nextflow and SLURM:

- each process can request different resources (CPUs, memory, time, GPUs)
- Nextflow can submit processes as job arrays
- Nextflow can resubmit processes which fail with additional resources (more below)

### Retry strategies

To illustrate the ability to resubmit jobs, the `demo-head.sl` script uses a configuration file (`oom.config`) which sets the initial resources for one of the processes to be too low to complete.
The configuration includes an error strategy that will retry tasks that fail with certain error codes typically associated with out of memory errors or timeouts.
The resources allocated to a task are set to a value multiplied by the task attempt number.
On the first attempt, the `multiqc` task is allocated 250Mb of memory, but if it fails, it will be resubmitted with 500Mb of memory and then 750Mb on the third attempt.
