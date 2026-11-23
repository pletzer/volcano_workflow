#!/bin/bash -e

# Run the Nextflow head process as a Slurm job, which submits each task as its own Slurm job.
# Extra arguments are passed to nextflow, e.g.
#
#   sbatch --account=<project> submit_mahuika.sl --account=<project> --outdir=/path/to/output
#
# Set PROFILE to use other profiles, e.g. PROFILE=test,mahuika sbatch submit_mahuika.sl
# If the job runs out of time, submit it again: -resume skips the tasks that have completed.

#SBATCH --job-name=volcano-nextflow
#SBATCH --time=04:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=2

module purge
module load Nextflow/26.04.0

# keep the Java virtual machine of the head process within the memory of the job
export NXF_OPTS="-Xms500M -Xmx3G"

nextflow run main.nf -profile "${PROFILE:-mahuika}" -resume "$@"
