#!/usr/bin/env nextflow

/*
 * Bayesian surface-wave tomography of the Auckland volcanic field:
 *   1. INV2D     2D Rayleigh-wave velocity inversion, one task per period and batch of chains
 *   2. MERGE2D   combine the batches of chains of each period into the 2D velocity maps
 *   3. MAKE_GRID gather the 2D results into one dispersion curve per grid point
 *   4. INV1D     1D shear-wave velocity inversion, one task per batch of grid points
 */

process INV2D {
    tag "${period}s batch ${batch}"

    input:
    tuple val(period), path(data), val(batch)

    output:
    tuple val(period), path("batch_${batch}.npz")

    script:
    def seed = params.seed != null ? "--seed=${params.seed}" : ''
    """
    source ${params.venv}/bin/activate
    inv2D.py --data=${data} --target-period=${period} --results-dir=. \\
        --cell-size=${params.cell_size} ${seed} \\
        --n-iterations=${params.inv2d_n_iterations} \\
        --burnin-iterations=${params.inv2d_burnin_iterations} \\
        --n-chains=${params.inv2d_n_chains} \\
        --chains-per-batch=${params.inv2d_chains_per_task} \\
        --batches=${batch} --partial
    """
}

process MERGE2D {
    tag "${period}s"
    publishDir "${params.outdir}/2D", mode: 'copy'

    input:
    tuple val(period), path(batches)

    // output the individual files rather than the directory: on -resume, publishDir skips
    // existing targets, so a file deleted from an existing output directory would not be restored
    output:
    tuple val(period), path("${period}s/*")

    script:
    """
    source ${params.venv}/bin/activate
    merge2D.py --batches ${batches} --target-period=${period} --results-dir=${period}s
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
    source ${params.venv}/bin/activate
    make_grid.py --data ${results} --periods ${periods.join(' ')} --results-dir=grid
    """
}

process INV1D {
    tag "${lons.first()}..${lons.last()} x ${lats.first()}..${lats.last()}"
    publishDir params.outdir, mode: 'copy'

    // a block of grid points: all the combinations of lons and lats, and their directories
    input:
    tuple val(lons), val(lats), path(points)
    val periods

    // individual files rather than directories, see INV2D
    output:
    path "1D/*/*"

    script:
    def seed = params.seed != null ? "--seed=${params.seed}" : ''
    def n_workers = Math.min(params.inv1d_parallel_points, lons.size() * lats.size())
    """
    source ${params.venv}/bin/activate
    inv1D.py --data=. --results-dir=1D \\
        --lons=${lons.join(',')} --lats=${lats.join(',')} --n-workers=${n_workers} \\
        --periods ${periods.join(' ')} ${seed} \\
        --n-iterations=${params.inv1d_n_iterations} \\
        --burnin-iterations=${params.inv1d_burnin_iterations} \\
        --n-chains=${params.inv1d_n_chains}
    """
}

/*
 * Split the grid point directories <lon>-<lat> written by MAKE_GRID into blocks of up to
 * n_lons x n_lats points. Returns one tuple (lons, lats, directories) per block, with the
 * coordinates as strings, exactly as in the directory names.
 */
def gridBlocks(dirs, n_lons, n_lats) {
    def points = dirs.collect { dir ->
        def match = dir.name =~ /^(-?[0-9.]+)-(-?[0-9.]+)$/
        if (!match.matches()) {
            error "unexpected grid point directory name: ${dir.name}"
        }
        [lon: match.group(1), lat: match.group(2), dir: dir]
    }
    // sort the coordinates so that the blocks, and hence the cached tasks, are the same in every run
    def lon_blocks = points.collect { p -> p.lon }.unique().sort { lon -> lon.toDouble() }.collate(n_lons)
    def lat_blocks = points.collect { p -> p.lat }.unique().sort { lat -> lat.toDouble() }.collate(n_lats)
    return lon_blocks.collectMany { lons ->
        lat_blocks.collect { lats ->
            def block = points.findAll { p -> p.lon in lons && p.lat in lats }
            if (block.size() != lons.size() * lats.size()) {
                error "the grid is not rectangular: ${block.size()} grid points in the block ${lons} x ${lats}"
            }
            tuple(lons, lats, block.collect { p -> p.dir })
        }
    }
}

workflow {
    // one input directory <period>s/ per period, containing data/
    def selected = params.periods != null ? params.periods.toString().tokenize(',')*.trim()*.toFloat() : null
    def inputs = channel.fromPath("${params.input}/*s", type: 'dir')
        .map { dir -> tuple(dir.name.replaceAll(/s$/, ''), dir.resolve('data')) }
        .filter { period, _data -> selected == null || (period.toFloat() in selected) }

    // one INV2D task per period and batch of chains, merged per period once all its batches are done
    if (params.inv2d_n_chains % params.inv2d_chains_per_task != 0) {
        error "inv2d_n_chains (${params.inv2d_n_chains}) must be a multiple of inv2d_chains_per_task (${params.inv2d_chains_per_task})"
    }
    def n_batches = params.inv2d_n_chains.intdiv(params.inv2d_chains_per_task)
    def batches = INV2D(inputs.combine(channel.of(0..<n_batches)))
        .groupTuple(size: n_batches)

    // recover the results directory of each period from its files
    def results_2d = MERGE2D(batches).map { period, files -> tuple(period, [files].flatten()[0].parent) }

    // sort by period so that the gathered dispersion curves are in a fixed order
    def gathered = results_2d.toSortedList { a, b -> a[0].toFloat() <=> b[0].toFloat() }
    def periods = gathered.map { list -> list.collect { item -> item[0] } }
    def dirs = gathered.map { list -> list.collect { item -> item[1] } }

    // one INV1D task per block of grid points
    def blocks = MAKE_GRID(periods, dirs)
        .flatMap { points -> gridBlocks([points].flatten(), params.inv1d_block_lons, params.inv1d_block_lats) }

    INV1D(blocks, periods)
}
