#!/usr/bin/env python3
import os

import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import defopt


def load_batches(paths):
    """
    Load the batch files written by inv2D.py --partial, in order of batch index
    so that the merged results do not depend on the order of the paths.
    """
    batches = [dict(np.load(path)) for path in paths]
    batches.sort(key=lambda batch: int(batch["batch"]))
    indices = [int(batch["batch"]) for batch in batches]
    if len(set(indices)) != len(indices):
        raise ValueError(f"duplicate batch indices {indices}")
    for name in ("grid_points", "extent"):
        for batch in batches[1:]:
            if not np.array_equal(batch[name], batches[0][name]):
                raise ValueError(f"batch {int(batch['batch'])} has a different {name} from batch {indices[0]}")
    return batches


def write_results(results_dir, target_period, batches, checksum=False):
    """
    Combine the batches of Markov chains and write the velocity maps to results_dir.

    :param batches: list of dicts with the keys of the files written by inv2D.py --partial
    """
    os.makedirs(results_dir, exist_ok=True)
    grid_points = batches[0]["grid_points"]
    lonmin, lonmax, latmin, latmax = batches[0]["extent"]

    sum_vel = np.zeros(grid_points.shape[0])
    sumsq_vel = np.zeros(grid_points.shape[0])
    n_samples_total = 0
    for batch in batches:
        sum_vel += batch["sum_vel"]
        sumsq_vel += batch["sumsq_vel"]
        n_samples_total += int(batch["n_samples"])

    inferred_vel = sum_vel / n_samples_total
    inferred_vel_std = np.sqrt(sumsq_vel / n_samples_total - inferred_vel**2)

    stat_mean = np.array([batch["mean"] for batch in batches]).mean(axis=0)
    stat_medi = np.array([batch["median"] for batch in batches]).mean(axis=0)
    stat_vstd = np.array([batch["std"] for batch in batches]).mean(axis=0)

    print(f"{n_samples_total} total samples accumulated across {len(batches)} batches")

    if checksum:
        for name, values in [("inferred_vel", inferred_vel), ("inferred_vel_std", inferred_vel_std),
                             ("mean_vel", stat_mean), ("medi_vel", stat_medi), ("std_vel", stat_vstd)]:
            print(f"checksum {name} {np.sum(np.abs(values)):.15e}")

    fig = plt.figure(figsize=(7, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([lonmin, lonmax, latmin, latmax], crs=ccrs.PlateCarree())

    img = ax.tricontourf(*grid_points.T, inferred_vel, levels=50, cmap="seismic_r",
                          extend='both', transform=ccrs.PlateCarree(), alpha=0.85)

    ax.add_feature(cfeature.NaturalEarthFeature('physical', 'coastline', '10m'),
                   linewidth=0.8, edgecolor='black', facecolor='none')
    ax.add_feature(cfeature.OCEAN, facecolor='lightblue', zorder=0)

    gl = ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.5)
    gl.top_labels = False
    gl.right_labels = False

    cbar = fig.colorbar(img, ax=ax, aspect=35, pad=0.02, shrink=0.8)
    cbar.set_label('Rayleigh-wave velocity [km/s]')
    fig.suptitle(f'Inferred velocity model, {target_period} s', y=0.93)
    fig.subplots_adjust(top=0.90)

    fig.canvas.draw()

    plt.savefig(os.path.join(results_dir, "velocity_map.png"), dpi=200)
    np.savetxt(os.path.join(results_dir, "inferred_vel.txt"), inferred_vel)
    np.savetxt(os.path.join(results_dir, "inferred_vel_std.txt"), inferred_vel_std)
    np.savetxt(os.path.join(results_dir, "mean_vel.txt"), stat_mean)
    np.savetxt(os.path.join(results_dir, "medi_vel.txt"), stat_medi)
    np.savetxt(os.path.join(results_dir, "std_vel.txt"), stat_vstd)
    np.savetxt(os.path.join(results_dir, "grid.txt"), grid_points)


def main(*, batches: list[str], target_period: float, results_dir: str, checksum: bool = False):
    """
    Merge the batches of Markov chains run separately by inv2D.py --partial into
    the same results as a single inv2D.py run with all the batches.

    :param batches: batch files batch_<index>.npz written by inv2D.py --partial
    :param target_period: target period in seconds, for the title of the velocity map
    :param results_dir: directory where the results are written
    :param checksum: print checksums of the results
    """
    write_results(results_dir, target_period, load_batches(batches), checksum)


if __name__ == "__main__":
    defopt.run(main)
