#!/usr/bin/env nextflow

/*
 * Bayesian surface-wave tomography of the Auckland volcanic field:
 *   1. INV2D     2D Rayleigh-wave velocity inversion, one task per period
 *   2. MAKE_GRID gather the 2D results into one dispersion curve per grid point
 *   3. INV1D     1D shear-wave velocity inversion, one task per batch of grid points
 */

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
    inv2D.py --data=${data} --target-period=${period} --results-dir=${period}s \\
        --cell-size=${params.cell_size} ${seed} \\
        --n-iterations=${params.inv2d_n_iterations} \\
        --burnin-iterations=${params.inv2d_burnin_iterations} \\
        --n-chains=${params.inv2d_n_chains}
    """
}

process MAKE_GRID {
    input:
    val periods
    path results

    output:
    path "grid/*", type: 'dir'

    script:
    """
    make_grid.py --data ${results} --periods ${periods.join(' ')} --results-dir=grid
    """
}

process INV1D {
    tag "${point.name}"
    publishDir params.outdir, mode: 'copy'
    maxForks params.inv1d_parallel_points   // number of grid points run at the same time

    input:
    path point
    val periods

    // individual files rather than directories, see INV2D
    output:
    path "1D/*/*"

    script:
    def seed = params.seed != null ? "--seed=${params.seed}" : ''
    """
    inv1D.py --data=${point} --results-dir=1D/${point} \\
        --periods ${periods.join(' ')} ${seed} \\
        --n-iterations=${params.inv1d_n_iterations} \\
        --burnin-iterations=${params.inv1d_burnin_iterations} \\
        --n-chains=${params.inv1d_n_chains}
    """
}

workflow {
    // one input directory <period>s/ per period, containing data/
    def selected = params.periods != null ? params.periods.toString().tokenize(',')*.trim()*.toFloat() : null
    def inputs = channel.fromPath("${params.input}/*s", type: 'dir')
        .map { dir -> tuple(dir.name.replaceAll(/s$/, ''), dir.resolve('data')) }
        .filter { period, _data -> selected == null || (period.toFloat() in selected) }

    // recover the results directory of each period from its files
    def results_2d = INV2D(inputs).map { period, files -> tuple(period, [files].flatten()[0].parent) }

    // sort by period so that the gathered dispersion curves are in a fixed order
    def gathered = results_2d.toSortedList { a, b -> a[0].toFloat() <=> b[0].toFloat() }
    def periods = gathered.map { list -> list.collect { item -> item[0] } }
    def dirs = gathered.map { list -> list.collect { item -> item[1] } }

    // one INV1D task per grid point
    def points = MAKE_GRID(periods, dirs).flatten()

    INV1D(points, periods)
}
