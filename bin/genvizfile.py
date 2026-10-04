import os
import glob

import numpy as np
import defopt
import shapely.geometry
from cartopy.io import shapereader
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import (vtkRectilinearGrid, vtkPolyData, vtkCellArray,
                                            vtkMultiBlockDataSet, vtkCompositeDataSet)
from vtkmodules.vtkIOXML import vtkXMLMultiBlockDataWriter
from vtkmodules.util.numpy_support import numpy_to_vtk


def cell_edges(centres):
    """Return the cell edges of a uniform 1D grid given its (increasing) cell centres."""
    dx = centres[1] - centres[0]
    return np.concatenate([centres - 0.5*dx, [centres[-1] + 0.5*dx]])


def get_coastline(xmin, xmax, ymin, ymax, resolution="10m"):
    """Return the Natural Earth coastline clipped to the box as a list of (n, 2) lon-lat arrays."""
    box = shapely.geometry.box(xmin, ymin, xmax, ymax)
    path = shapereader.natural_earth(resolution=resolution, category="physical", name="coastline")
    lines = []
    for geom in shapereader.Reader(path).geometries():
        if not geom.intersects(box):
            continue
        clipped = geom.intersection(box)
        parts = getattr(clipped, "geoms", [clipped])
        lines += [np.array(part.coords) for part in parts
                  if isinstance(part, shapely.geometry.LineString) and len(part.coords) >= 2]
    return lines


def build_coastline(lines):
    """Return the coastline segments as VTK polylines in the z = 0 plane."""
    points = vtkPoints()
    cells = vtkCellArray()
    for line in lines:
        start = points.GetNumberOfPoints()
        for x, y in line[:, :2]:
            points.InsertNextPoint(x, y, 0.0)
        cells.InsertNextCell(len(line), range(start, start + len(line)))
    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetLines(cells)
    return polydata


def main(*, results_dir: str, output: str):
    """
    Convert the inv2D.py results into a VTK multiblock (.vtm) file with two blocks:
    "velocity", a rectilinear grid with the velocity fields stored as cell data, and
    "coastline", the coastline clipped to the same domain. The blocks are written to
    files in a directory next to the .vtm file, named after it without the suffix.

    :param results_dir: directory containing grid.txt and the *_vel*.txt files
    :param output: name of the output .vtm file
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

    coastline = get_coastline(xedges[0], xedges[-1], yedges[0], yedges[-1])

    blocks = vtkMultiBlockDataSet()
    for k, (name, block) in enumerate([("velocity", rgrid), ("coastline", build_coastline(coastline))]):
        blocks.SetBlock(k, block)
        blocks.GetMetaData(k).Set(vtkCompositeDataSet.NAME(), name)

    if not output.endswith(".vtm"):
        output += ".vtm"

    writer = vtkXMLMultiBlockDataWriter()
    writer.SetFileName(output)
    writer.SetInputData(blocks)
    if writer.Write() != 1:
        raise RuntimeError(f"failed to write {output}")
    print(f"wrote {nx} x {ny} cells, {rgrid.GetCellData().GetNumberOfArrays()} fields and "
          f"{len(coastline)} coastline segments to {output}")


if __name__ == '__main__':
    defopt.run(main)
