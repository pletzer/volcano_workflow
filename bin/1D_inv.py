import bayesbay as bb
from bayesbay.discretization import Voronoi1D
import numpy as np
import matplotlib.pyplot as plt
from disba import PhaseDispersion, GroupDispersion
import os
import random
import defopt


def parse_args(*, data: str, results_dir: str,
               checksum: bool = False, seed: int = None,
               n_iterations: int = 50_000, burnin_iterations: int = 10_000,
               n_chains: int = 8):
    """
    Bayesian 1D shear-wave velocity inversion of a Rayleigh-wave group-velocity
    dispersion curve using bayesbay.

    :param data: directory containing disp.disp
    :param results_dir: directory where the results are written
    :param checksum: print checksums of the results (use with --seed for reproducible values)
    :param seed: seed of the random number generators, for reproducible runs
    :param n_iterations: number of iterations per Markov chain
    :param burnin_iterations: number of burn-in iterations per Markov chain
    :param n_chains: number of Markov chains
    """
    return (data, results_dir, checksum, seed,
            n_iterations, burnin_iterations, n_chains)


(disp_dir, results_dir, checksum, seed,
 n_iterations, burnin_iterations, n_chains) = defopt.run(parse_args)
os.makedirs(results_dir, exist_ok=True)

# bayesbay draws from the global random and numpy.random generators. When seeded,
# the chains run in this process (n_jobs=1) so that the results are reproducible
if seed is not None:
    random.seed(seed)
    np.random.seed(seed)

#THICKNESS = np.array([10, 10, 15, 20, 20, 20, 20, 20, 0])
#VS = np.array([3.38, 3.44, 3.66, 4.25, 4.35, 4.32, 4.315, 4.38, 4.5])

THICKNESS = np.array([20, 15, 0])
VS = np.array([3.36, 3.75, 4.47])
VP_VS = 1.77
VP = VS * VP_VS
RHO = 0.32 * VP + 0.77
PERIODS = np.arange(2,25.5,0.5)  #np.geomspace(3, 80, 20)
RAYLEIGH_STD = 0.02

def initialize_vs(param, positions=None):
    vmin, vmax = param.get_vmin_vmax(positions)
    sorted_vals = np.sort(np.random.uniform(vmin, vmax, positions.size))
    return sorted_vals

vs = bb.prior.UniformPrior(name="vs", 
                                    vmin=[2, 2, 2], 
                                    vmax=[5, 5, 5], 
                                    position=[0, 20, 60],
                                    perturb_std=0.15)
vs.set_custom_initialize(initialize_vs)

#pd = PhaseDispersion(THICKNESS, VP, VS, RHO)
#phase_vel = pd(PERIODS, mode=0, wave="rayleigh").velocity
gd = GroupDispersion(THICKNESS, VP, VS, RHO)
group_vel = gd(PERIODS, mode=0, wave="rayleigh").velocity
d_obs = np.loadtxt(os.path.join(disp_dir, "disp.disp")) #phase_vel + np.random.normal(0, RAYLEIGH_STD, phase_vel.size)

# For plotting the prior
depth_prior = np.linspace(0, 200)
vmin_prior, vmax_prior = vs.get_vmin_vmax(depth_prior)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4), gridspec_kw={'width_ratios': [1, 2.5]})
ax1.fill_betweenx(depth_prior, vmin_prior, vmax_prior, alpha=0.2, label='Prior')
Voronoi1D.plot_tessellation(THICKNESS, 
                            VS, 
                            label='True Vs', 
                            ax=ax1, 
                            color='k', 
                            lw=2, 
                            input_type='extents')
ax1.set_xlabel('Vs [km/s]')
ax1.set_ylabel('Depth [km]')
ax1.set_ylim(np.cumsum(THICKNESS)[-1] + max(THICKNESS), 0)
ax1.grid()
ax1.legend()

ax2.plot(PERIODS, group_vel, 'r--', label='Rayleigh (true Vs)', lw=0.5)
ax2.plot(PERIODS, d_obs, 'ro', label='Rayleigh obs.')
ax2.set_xlabel('Period [s]')
ax2.set_ylabel('Group velocity [km/s]')
ax2.grid()
ax2.legend()

plt.tight_layout(w_pad=2)
plt.savefig(os.path.join(results_dir, "fig1.pdf"))

voronoi = Voronoi1D(
    name="voronoi", 
    vmin=0,
    vmax=150,
    perturb_std=10,
    n_dimensions=None, 
    n_dimensions_min=4,
    n_dimensions_max=15,
    parameters=[vs], 
    birth_from='neighbour'
)
parameterization = bb.parameterization.Parameterization(voronoi)

def compute_cell_extents(voronoi_sites):
    # the extent of the unbounded bottom cell (half-space) should be 0, but some
    # builds of bayesbay's compiled extension return inf, which yields NaNs downstream
    thickness = Voronoi1D.compute_cell_extents(voronoi_sites)
    thickness[~np.isfinite(thickness)] = 0
    return thickness

def forward_sw(state):
    voronoi = state["voronoi"]
    voronoi_sites = voronoi["discretization"]
    thickness = compute_cell_extents(voronoi_sites)
    vs = voronoi["vs"]
    vp = vs * VP_VS
    rho = 0.32 * vp + 0.77
    #pd = PhaseDispersion(thickness, vp, vs, rho)
    gd = GroupDispersion(thickness, vp, vs, rho)
    d_pred = gd(PERIODS, mode=0, wave="rayleigh").velocity
    if len(d_pred) != len(PERIODS):
        return np.full(PERIODS.shape, np.nan)
    return d_pred

target = bb.likelihood.Target("rayleigh", 
                   d_obs, 
                   std_min=0.001, 
                   std_max=0.2, 
                   std_perturb_std=0.002)

log_likelihood = bb.likelihood.LogLikelihood(targets=target, fwd_functions=forward_sw)

inversion = bb.BayesianInversion(
    parameterization=parameterization, 
    log_likelihood=log_likelihood,
    n_chains=n_chains
)

print(np.shape(target.dobs))

inversion.run(
    sampler=None, 
    n_iterations=n_iterations, 
    burnin_iterations=burnin_iterations, 
    save_every=150,
    verbose=False,
    **({"parallel_config": {"n_jobs": 1}} if seed is not None else {}),
)

for chain in inversion.chains:
    chain.print_statistics()

results = inversion.get_results(concatenate_chains=True)

sampled_voronoi_nuclei = results['voronoi.discretization']
sampled_thickness = [compute_cell_extents(n) for n in sampled_voronoi_nuclei]
sampled_vs = results['voronoi.vs']
interp_depths = np.linspace(0, 160, 160)
statistics_vs = Voronoi1D.get_tessellation_statistics(
    sampled_thickness, sampled_vs, interp_depths, input_type='extents'
    )

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6, 8), gridspec_kw={'width_ratios': [2.5, 1]})
ax1, cbar = Voronoi1D.plot_tessellation_density(sampled_thickness, 
                                                sampled_vs, 
                                                input_type='extents', 
                                                ax=ax1, 
                                                cmap='binary', 
                                                vmin=0, 
                                                vmax=2000)
Voronoi1D.plot_tessellation(THICKNESS, 
                            VS, 
                            ax=ax1, 
                            color='yellow', 
                            lw=3, 
                            label='True Vs',
                            input_type='extents')
ax1.plot(statistics_vs['mean'], interp_depths, 'b', lw=2, label='Vs Ensemble Mean')
ax1.plot(statistics_vs['median'], interp_depths, 'r', lw=2, label='Vs Ensemble Median')
ax1.set_xlabel("Vs [km/s]")
ax1.set_ylabel("Depth [km]")
ax1.legend()

Voronoi1D.plot_interface_hist(sampled_voronoi_nuclei, bins=75, ec='w', ax=ax2)
ax2.tick_params(labelleft=False)
ax2.set_ylabel('')
ax2.set_ylim(*ax1.get_ylim())
plt.tight_layout()
plt.savefig(os.path.join(results_dir, "fig2.pdf"))

if checksum:
    for name, values in [("mean", statistics_vs['mean']), ("medi", statistics_vs['median'])]:
        print(f"checksum {name} {np.sum(np.abs(values)):.15e}")

np.savetxt(os.path.join(results_dir, "mean.txt"), np.array(statistics_vs['mean']))
np.savetxt(os.path.join(results_dir, "medi.txt"), np.array(statistics_vs['median']))
np.savetxt(os.path.join(results_dir, "dpth.txt"), np.array(interp_depths))

#d_pred = np.array(results['rayleigh.dpred'])
#percentiles = np.percentile(d_pred, (10, 90), axis=0)

# Predicted dispersion curves
#fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 6))
#ax1.plot(PERIODS, group_vel, 'r--', label='Rayleigh (true Vs)', lw=0.5)
#ax1.plot(PERIODS, d_obs, 'ro', label='Observations')
#ax1.fill_between(PERIODS, percentiles[0], percentiles[1], color='r', alpha=0.2, label='Inferred Data (10th-90th percentiles)', zorder=100)
#ax1.set_xlabel('Period [s]')
#ax1.set_ylabel('Group velocity [km/s]')
#ax1.grid()
#ax1.legend()

# Histogram of inferred data noise
#ax2.axvline(x=RAYLEIGH_STD, color='r', lw=3, alpha=0.3, label='True data noise')
#pdf, bins, _ = ax2.hist(results['rayleigh.std'], density=True, bins=20, ec='w', zorder=100, label='Posterior')
#ax2.fill_between([target.std_min, target.std_max], 1 / (target.std_max - target.std_min), alpha=0.2, label='Prior')
#ax2.set_xlabel('Noise standard deviation')
#ax2.ticklabel_format(style='sci', axis='x', scilimits=(0,0))
#ax2.legend(framealpha=0.9)
#plt.tight_layout()
#plt.savefig('fig3.pdf')


#def get_subplot_layout(n_subplots):
#    rows = int(np.sqrt(n_subplots))
#    cols = int(np.ceil(n_subplots / rows))
#    return rows, cols

#rows, cols = get_subplot_layout(len(inversion.chains))
#fig, axes = plt.subplots(rows, cols, figsize=(15, 15))
#for ipanel, (ax, chain) in enumerate(zip(np.ravel(axes), inversion.chains)):
#    saved_states = chain.saved_states
#    saved_nuclei = saved_states["voronoi.discretization"]
#    saved_vs = saved_states['voronoi.vs']
#    
#    Voronoi1D.plot_tessellations(saved_nuclei,
#                                 saved_vs, 
#                                 ax=ax, 
#                                 linewidth=0.1, 
#                                 color="k", 
#                                 bounds=(0, 150))
#    Voronoi1D.plot_tessellation(THICKNESS, 
#                                VS, 
#                                color='yellow', 
#                                lw=2, 
#                                ax=ax,
#                                input_type='extents')
#    Voronoi1D.plot_tessellation_statistics(
#        saved_nuclei, saved_vs, interp_depths, ax=ax
#    )
#    
#    ax.set_title(f'Chain {chain.id}')
#    ax.tick_params(direction='in', labelleft=False, labelbottom=False)
#    ax.set_xlabel('')
#    ax.set_ylabel('')
#    
#    if not ipanel % cols:
#        ax.set_ylabel('Depth [km]')
#        ax.tick_params(labelleft=True)
#    if ipanel >= (rows-1) * cols:
#        ax.set_xlabel('Vs [km/s]')
#        ax.tick_params(labelbottom=True)
#    
#plt.tight_layout()
#plt.savefig('fig4.pdf')
