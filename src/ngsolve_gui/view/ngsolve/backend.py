"""The ngsolve backend: meshes, regions, geometries and coefficient functions."""

import ngsolve as ngs
from netgen import occ


def target(obj):
    if isinstance(obj, occ.TopoDS_Shape):
        return "geometry", occ.OCCGeometry(obj)
    if isinstance(obj, occ.OCCGeometry):
        return "geometry", obj
    if isinstance(obj, (ngs.Mesh, ngs.Region)):
        return "mesh", obj
    if isinstance(obj, ngs.CoefficientFunction):
        return "function", obj
    try:
        return "function", ngs.CF(obj)
    except Exception:
        return None
