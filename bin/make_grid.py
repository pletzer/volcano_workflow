import os

import numpy as np
import defopt


def main(*, data: list[str], periods: list[float], results_dir: str):
    """
    Gather the inv2D.py results of several periods into one dispersion curve per
    grid point. For each grid point, a directory named <lon>-<lat> is created in
    results_dir, containing a file disp.disp with the inferred velocity at each
    period, in order of increasing period.

    :param data: directories containing grid.txt and inferred_vel.txt, one per period
    :param periods: periods in seconds, in the same order as data
    :param results_dir: directory where the grid point directories are written
    """
    if len(data) != len(periods):
        raise ValueError(f"got {len(data)} data directories but {len(periods)} periods")
    if len(set(periods)) != len(periods):
        raise ValueError(f"duplicate periods in {periods}")

    # the data directories may be supplied in any order
    order = np.argsort(periods)
    data = [data[k] for k in order]

    grid_coords = np.loadtxt(os.path.join(data[0], "grid.txt"))
    N = np.shape(grid_coords)[0]

    vel = np.empty((N, len(data)))
    for j, disp_dir in enumerate(data):
        # all periods must have been inverted on the same grid
        grid_j = np.loadtxt(os.path.join(disp_dir, "grid.txt"))
        if not np.array_equal(grid_j, grid_coords):
            raise ValueError(f"grid.txt in {disp_dir} differs from the one in {data[0]}")
        vel_j = np.loadtxt(os.path.join(disp_dir, "inferred_vel.txt"))
        if vel_j.shape != (N,):
            raise ValueError(f"inferred_vel.txt in {disp_dir} has shape {vel_j.shape}, expected ({N},)")
        vel[:, j] = vel_j

    for i in range(N):
        lon = grid_coords[i,0]
        lat = grid_coords[i,1]
        to_dir = os.path.join(results_dir, str(lon)+'-'+str(lat))
        os.makedirs(to_dir, exist_ok=True)
        np.savetxt(os.path.join(to_dir, 'disp.disp'), vel[i, :])

    print(f"wrote {N} dispersion curves of {len(data)} periods to {results_dir}")


if __name__ == '__main__':
    defopt.run(main)
