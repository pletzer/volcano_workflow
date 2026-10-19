process INV1D {
    tag "${points[0].name} (${points.size()} points)"
    publishDir params.outdir, mode: 'copy'

    input:
    path points
    val periods

    // individual files rather than directories, see INV2D
    output:
    path "1D/*/*"

    script:
    def seed = params.seed != null ? "--seed=${params.seed}" : ''
    """
    source ${params.venv}/bin/activate
    for point in ${points}; do
        inv1D.py --data=\$point --results-dir=1D/\$point \\
            --periods ${periods.join(' ')} ${seed} \\
            --n-iterations=${params.inv1d_n_iterations} \\
            --burnin-iterations=${params.inv1d_burnin_iterations} \\
            --n-chains=${params.inv1d_n_chains}
    done
    """
}