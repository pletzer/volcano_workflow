import os
import glob

import numpy as np
import defopt
from vtkmodules.vtkCommonDataModel import vtkRectilinearGrid
from vtkmodules.vtkIOXML import vtkXMLRectilinearGridWriter
from vtkmodules.util.numpy_support import numpy_to_vtk


def cell_edges(centres):
    """Return the cell edges of a uniform 1D grid given its (increasing) cell centres."""
    dx = centres[1] - centres[0]
    return np.concatenate([centres - 0.5*dx, [centres[-1] + 0.5*dx]])


def main(*, results_dir: str, output: str):
    """
    Convert the bayesbay2D.py results into a VTK rectilinear grid (.vtr) file
    with the velocity fields stored as cell data.

    :param results_dir: directory containing grid.txt and the *_vel*.txt files
    :param output: name of the output .vtr file
    """
    # cell centres (lon, lat), longitude varies fastest
    grid = np.loadtxt(os.path.join(results_dir, "grid.txt"))
    lons = np.unique(grid[:, 0])
    lats = np.unique(grid[:, 1])
    nx, ny = len(lons), len(lats)
    if nx*ny != grid.shape[0]:
        raise ValueError(f"grid.txt has {grid.shape[0]} points, not a {nx} x {ny} tensor product grid")

    # map each point to its (i, j) cell index, so that the data can be reordered
    # to VTK's ordering (x fastest, increasing coordinates)
    i = np.searchsorted(lons, grid[:, 0])
    j = np.searchsorted(lats, grid[:, 1])
    vtk_index = i + nx*j

    xedges = cell_edges(lons)
    yedges = cell_edges(lats)

    rgrid = vtkRectilinearGrid()
    rgrid.SetDimensions(nx + 1, ny + 1, 1)
    rgrid.SetXCoordinates(numpy_to_vtk(xedges, deep=True))
    rgrid.SetYCoordinates(numpy_to_vtk(yedges, deep=True))
    rgrid.SetZCoordinates(numpy_to_vtk(np.zeros(1), deep=True))

    for filename in sorted(glob.glob(os.path.join(results_dir, "*_vel*.txt"))):
        values = np.loadtxt(filename)
        if values.shape != (grid.shape[0],):
            raise ValueError(f"{filename} has shape {values.shape}, expected ({grid.shape[0]},)")
        cell_values = np.empty_like(values)
        cell_values[vtk_index] = values
        array = numpy_to_vtk(cell_values, deep=True)
        array.SetName(os.path.splitext(os.path.basename(filename))[0])
        rgrid.GetCellData().AddArray(array)

    if not output.endswith(".vtr"):
        output += ".vtr"

    writer = vtkXMLRectilinearGridWriter()
    writer.SetFileName(output)
    writer.SetInputData(rgrid)
    if writer.Write() != 1:
        raise RuntimeError(f"failed to write {output}")
    print(f"wrote {nx} x {ny} cells, {rgrid.GetCellData().GetNumberOfArrays()} fields to {output}")


if __name__ == '__main__':
    defopt.run(main)
