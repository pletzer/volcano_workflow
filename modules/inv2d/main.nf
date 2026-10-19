process INV2D {
    tag "${period}s"
    publishDir "${params.outdir}/2D", mode: 'copy'

    input:
    tuple val(period), path(data)

    // output the individual files rather than the directory: on -resume, publishDir skips
    // existing targets, so a file deleted from an existing output directory would not be restored
    output:
    tuple val(period), path("${period}s/*")

    script:
    def seed = params.seed != null ? "--seed=${params.seed}" : ''
    """
    source ${params.venv}/bin/activate
    inv2D.py --data=${data} --target-period=${period} --results-dir=${period}s \\
        --cell-size=${params.cell_size} ${seed} \\
        --n-iterations=${params.inv2d_n_iterations} \\
        --burnin-iterations=${params.inv2d_burnin_iterations} \\
        --n-chains=${params.inv2d_n_chains}
    """
}