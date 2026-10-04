import numpy as np
import matplotlib.pyplot as plt
import scipy
from obspy.clients.fdsn import Client
import obspy as ob

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np

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


def parse_args(*, data: str, target_period: float, results_dir: str,
               checksum: bool = False, seed: int = None,
               n_iterations: int = 50_000, burnin_iterations: int = 10_000,
               n_chains: int = 8):
    """
    Bayesian 2D Rayleigh-wave velocity inversion using bayesbay.

    :param data: directory containing sources.dat and observed_t.dat
    :param target_period: target period in seconds
    :param results_dir: directory where the results are written
    :param checksum: print checksums of the results (use with --seed for reproducible values)
    :param seed: seed of the random number generators, for reproducible runs
    :param n_iterations: number of iterations per Markov chain
    :param burnin_iterations: number of burn-in iterations per Markov chain
    :param n_chains: total number of Markov chains, must be a multiple of 4
    """
    return (data, target_period, results_dir, checksum, seed,
            n_iterations, burnin_iterations, n_chains)


(disp_dir, target_period, results_dir, checksum, seed,
 n_iterations, burnin_iterations, n_chains_total) = defopt.run(parse_args)
os.makedirs(results_dir, exist_ok=True)

# bayesbay draws from the global random and numpy.random generators. The chains
# run in this process (n_jobs=1), so seeding both makes the results reproducible
if seed is not None:
    random.seed(seed)
    np.random.seed(seed)

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
cell_size = 0.05

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


chains_per_batch = 4
if n_chains_total % chains_per_batch != 0:
    raise ValueError(f"--n-chains must be a multiple of {chains_per_batch}")
n_batches = n_chains_total // chains_per_batch

save_every = 200

sum_vel = np.zeros(grid_points.shape[0])
sumsq_vel = np.zeros(grid_points.shape[0])
n_samples_total = 0

target = bb.likelihood.Target("rayleigh",
                              d_obs,
                              std_min=0.05,
                              std_max=0.2,
                              std_perturb_std=0.002)

log_likelihood = bb.likelihood.LogLikelihood(targets=target, fwd_functions=forward)

sum_std = []
sum_mea = []
sum_med = []

for b in tqdm(range(n_batches), desc="batches"):
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

    sum_vel += interp_vel_batch.sum(axis=0)
    sumsq_vel += (interp_vel_batch ** 2).sum(axis=0)
    n_samples_total += interp_vel_batch.shape[0]

    samp_nuclei = results_batch['voronoi.discretization']
    samp_vel = results_batch['voronoi.vel']
    stat_vec = Voronoi2D.get_tessellation_statistics(samp_nuclei, samp_vel, grid_points)

    sum_std += [stat_vec['std']]
    sum_mea += [stat_vec['mean']]
    sum_med += [stat_vec['median']]

    del inversion_batch, results_batch, interp_vel_batch, samp_nuclei, samp_vel
    gc.collect()
    get_reusable_executor().shutdown(wait=True)

inferred_vel = sum_vel / n_samples_total
inferred_vel_std = np.sqrt(sumsq_vel / n_samples_total - inferred_vel**2)

stat_mean = np.array(sum_mea).mean(axis=0)
stat_medi = np.array(sum_med).mean(axis=0)
stat_vstd = np.array(sum_std).mean(axis=0)

print(f"{n_samples_total} total samples accumulated across {n_batches} batches "
      f"({chains_per_batch} chains each)")

if checksum:
    for name, values in [("inferred_vel", inferred_vel), ("inferred_vel_std", inferred_vel_std),
                         ("mean_vel", stat_mean), ("medi_vel", stat_medi), ("std_vel", stat_vstd)]:
        print(f"checksum {name} {np.sum(np.abs(values)):.15e}")



fig = plt.figure(figsize=(7, 6))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([tomo.grid.lonmin, tomo.grid.lonmax, tomo.grid.latmin, tomo.grid.latmax], crs=ccrs.PlateCarree())

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
np.savetxt(os.path.join(results_dir, "mean_vel.txt"), stat_mean) #np.array(stat_vec['mean']))
np.savetxt(os.path.join(results_dir, "medi_vel.txt"), stat_medi) #np.array(stat_vec['median']))
np.savetxt(os.path.join(results_dir, "std_vel.txt"), stat_vstd) #np.array(stat_vec['std']))
np.savetxt(os.path.join(results_dir, "grid.txt"), grid_points)
#plt.show()
