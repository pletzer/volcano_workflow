#!/usr/bin/env python3
import numpy as np
import scipy
from obspy.clients.fdsn import Client
import obspy as ob

import gc
from tqdm.auto import tqdm

from seislib.tomography import SeismicTomography

from bayesbay.discretization import Voronoi2D
from bayesbay.prior import UniformPrior
import bayesbay as bb

import os
import glob
import random
from joblib.externals.loky import get_reusable_executor
import defopt

from merge2D import write_results


def parse_args(*, data: str, target_period: float, results_dir: str,
               checksum: bool = False, seed: int = None,
               n_iterations: int = 50_000, burnin_iterations: int = 10_000,
               n_chains: int = 8, chains_per_batch: int = 4, batches: list[int] = None,
               partial: bool = False, cell_size: float = 0.05):
    """
    Bayesian 2D Rayleigh-wave velocity inversion using bayesbay.

    :param data: directory containing sources.dat and observed_t.dat
    :param target_period: target period in seconds
    :param results_dir: directory where the results are written
    :param checksum: print checksums of the results (use with --seed for reproducible values)
    :param seed: seed of the random number generators, for reproducible runs. Batch b
        is seeded with seed + b, so its results do not depend on the other batches
    :param n_iterations: number of iterations per Markov chain
    :param burnin_iterations: number of burn-in iterations per Markov chain
    :param n_chains: total number of Markov chains, must be a multiple of chains_per_batch
    :param chains_per_batch: number of Markov chains run together and summarised by one
        set of tessellation statistics
    :param batches: indices of the batches to run, from 0 to n_chains/chains_per_batch - 1
        (default all)
    :param partial: write the results of each batch to batch_<index>.npz in results_dir,
        to be combined with merge2D.py, instead of the velocity maps
    :param cell_size: size of the grid cells in degrees
    """
    return (data, target_period, results_dir, checksum, seed,
            n_iterations, burnin_iterations, n_chains, chains_per_batch, batches, partial, cell_size)


(disp_dir, target_period, results_dir, checksum, seed,
 n_iterations, burnin_iterations, n_chains_total, chains_per_batch, batches, partial,
 cell_size) = defopt.run(parse_args)

if n_chains_total % chains_per_batch != 0:
    raise ValueError(f"--n-chains must be a multiple of --chains-per-batch ({chains_per_batch})")
n_batches = n_chains_total // chains_per_batch
if batches is None:
    batches = list(range(n_batches))
for b in batches:
    if not 0 <= b < n_batches:
        raise ValueError(f"batch {b} is out of range, there are {n_batches} batches")
os.makedirs(results_dir, exist_ok=True)

station_coords = np.loadtxt(os.path.join(disp_dir, "sources.dat"),skiprows=1)
stat_pairs = []
stat_dist = []

#print(np.shape(station_coords))
#print(station_coords[:,0])
#print(station_coords[0,:])

N = np.shape(station_coords)[0]
for i in range(N):
    for j in range(N):
        stat_pairs += [[station_coords[i,1],station_coords[i,0],station_coords[j,1],station_coords[j,0]]]
        lat1 = station_coords[i,1]
        lon1 = station_coords[i,0]
        lat2 = station_coords[j,1]
        lon2 = station_coords[j,0]
        if i==j:
            stat_dist += [0]
        else:
            stat_dist += [ob.geodetics.gps2dist_azimuth(lat1,lon1,lat2,lon2)[0]/1000]

stat_pairs = np.array(stat_pairs)
stat_dist = np.array(stat_dist)
travel_times = np.loadtxt(os.path.join(disp_dir, "observed_t.dat"),usecols=1)
print(np.shape(travel_times))
mask = travel_times > 0
#mask_mat = mask[:,None]
#mask_mat = np.concatenate((mask_mat,mask_mat,mask_mat,mask_mat),axis=1)
#print(np.shape(mask_mat))
d_obs = travel_times[mask]/stat_dist[mask]

period_tol = 0.5


def resolve_station(code, coords_lookup):
    if code in coords_lookup:
        return code
    for n in range(1, len(code)):
        candidate = code[:-n]
        if candidate in coords_lookup:
            return candidate
    return None


pad = 0.1

lats = station_coords[:,1] #[station_coords[s][0] for s in used_stations]
lons = station_coords[:,0] #[station_coords[s][1] for s in used_stations]

tomo = SeismicTomography(
    cell_size=cell_size,
    lonmin=min(lons) - pad, lonmax=max(lons) + pad,
    latmin=min(lats) - pad, latmax=max(lats) + pad,
    regular_grid=True
)
grid_points = np.column_stack(tomo.grid.midpoints_lon_lat())


def compute_jacobian(tomo):
    tomo.compile_coefficients()
    jacobian = scipy.sparse.csr_matrix(tomo.A)
    del tomo.A
    return jacobian

print(np.shape(stat_pairs))
tomo.data_coords = stat_pairs[mask,:]
print(np.shape(tomo.data_coords))
jacobian = compute_jacobian(tomo)




vel = UniformPrior('vel', vmin=1.5, vmax=4.0, perturb_std=0.1)  
voronoi = Voronoi2D(
    name='voronoi',
    vmin=[tomo.grid.lonmin, tomo.grid.latmin],
    vmax=[tomo.grid.lonmax, tomo.grid.latmax],
    perturb_std=0.05,
    n_dimensions_min=50,
    n_dimensions_max=1500,
    parameters=[vel],
    interpolation_positions=grid_points)
parameterization = bb.parameterization.Parameterization(voronoi)



def forward(state):
    voronoi_state = state["voronoi"]
    interp_vel = voronoi.get_interpolated_values(voronoi_state, "vel")
    state.save_to_extra_storage("interp_vel", interp_vel)
    return jacobian @ (1 / interp_vel)


save_every = 200

target = bb.likelihood.Target("rayleigh",
                              d_obs,
                              std_min=0.05,
                              std_max=0.2,
                              std_perturb_std=0.002)

log_likelihood = bb.likelihood.LogLikelihood(targets=target, fwd_functions=forward)

extent = np.array([tomo.grid.lonmin, tomo.grid.lonmax, tomo.grid.latmin, tomo.grid.latmax])
batch_results = []

for b in tqdm(batches, desc="batches"):
    # bayesbay draws from the global random and numpy.random generators. The chains
    # run in this process (n_jobs=1), so seeding both makes the results reproducible
    if seed is not None:
        random.seed(seed + b)
        np.random.seed(seed + b)

    inversion_batch = bb.BayesianInversion(
        parameterization=parameterization,
        log_likelihood=log_likelihood,
        n_chains=chains_per_batch,
        save_dpred=False,
    )
    inversion_batch.run(
        sampler=None,
        n_iterations=n_iterations,
        burnin_iterations=burnin_iterations,
        save_every=save_every,
        verbose=False,
        print_every=25_000,
        parallel_config={"n_jobs": 1},
    )
    results_batch = inversion_batch.get_results()
    interp_vel_batch = np.asarray(results_batch['interp_vel'])

    samp_nuclei = results_batch['voronoi.discretization']
    samp_vel = results_batch['voronoi.vel']
    stat_vec = Voronoi2D.get_tessellation_statistics(samp_nuclei, samp_vel, grid_points)

    batch_result = dict(batch=b, grid_points=grid_points, extent=extent,
                        sum_vel=interp_vel_batch.sum(axis=0),
                        sumsq_vel=(interp_vel_batch ** 2).sum(axis=0),
                        n_samples=interp_vel_batch.shape[0],
                        mean=np.asarray(stat_vec['mean']),
                        median=np.asarray(stat_vec['median']),
                        std=np.asarray(stat_vec['std']))
    if partial:
        np.savez(os.path.join(results_dir, f"batch_{b}.npz"), **batch_result)
    else:
        batch_results.append(batch_result)

    del inversion_batch, results_batch, interp_vel_batch, samp_nuclei, samp_vel
    gc.collect()
    get_reusable_executor().shutdown(wait=True)

if not partial:
    write_results(results_dir, target_period, batch_results, checksum)
