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