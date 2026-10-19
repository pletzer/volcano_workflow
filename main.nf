#!/usr/bin/env nextflow

/*
 * Bayesian surface-wave tomography of the Auckland volcanic field:
 *   1. INV2D     2D Rayleigh-wave velocity inversion, one task per period
 *   2. MAKE_GRID gather the 2D results into one dispersion curve per grid point
 *   3. INV1D     1D shear-wave velocity inversion, one task per batch of grid points
 */

include { INV2D } from './modules/inv2d/main.nf'
include { MAKE_GRID } from './modules/make_grid/main.nf'
include { INV1D } from './modules/inv1d/main.nf'

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

    def points = MAKE_GRID(periods, dirs)

    // sort the grid points so that the batches, and hence the cached tasks, are the same in every run
    def batches = points.flatten()
        .toSortedList { a, b -> a.name <=> b.name }
        .flatMap()
        .collate(params.inv1d_batch_size)

    INV1D(batches, periods)
}
