#!/bin/bash -e

#SBATCH --job-name=nextflow-demo-head
#SBATCH --output=log/%x_%j.out
#SBATCH --error=log/%x_%j.err
#SBATCH --mail-type=END
#SBATCH --time=01:00:00
#SBATCH --mem=3G
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4

module purge
module load Nextflow/26.04.0
export NXF_APPTAINER_CACHEDIR=/nesi/nobackup/nesi99999/apptainer_cache
export NXF_PLUGINS_DIR=/nesi/project/nesi99999/.nextflow/plugins

nextflow run nf-core/demo -r 1.2.0 -profile test_full,apptainer,mahuika \
    -w /nesi/nobackup/nesi99999/jreeve/nextflow-demo/work \
    --outdir /nesi/nobackup/nesi99999/jreeve/nextflow-demo/out \
    -c oom.config
