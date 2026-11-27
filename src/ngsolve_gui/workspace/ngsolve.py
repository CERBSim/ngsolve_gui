"""Inspectors for ngsolve and netgen objects."""

import ngsolve as ngs
from netgen import occ

from . import Entry, register_inspector, register_memory


def _space(fes):
    return fes.type or type(fes).__name__


def _mesh(name, mesh):
    regions, counts = (), ()
    for kind, label, names in (("material", "materials", mesh.GetMaterials()),
                               ("boundary", "boundaries", mesh.GetBoundaries())):
        indices = {}
        for i, n in enumerate(names):
            indices.setdefault(n, []).append(i)
        regions += tuple((kind, tuple(ii), n) for n, ii in indices.items())
        counts += ((label, len(indices)),)
    return Entry(name, "Mesh", "mdi-vector-triangle",
                 (("dimension", mesh.dim), ("elements", mesh.ne), ("vertices", mesh.nv),
                  ("facets", mesh.nfacet), *counts),
                 regions, drawable=True, mesh_id=id(mesh), target=True)


def _fes(name, fes):
    details = (("type", _space(fes)), ("mesh", f"{fes.mesh.dim}D mesh", id(fes.mesh)),
               ("order", fes.globalorder), ("ndof", fes.ndof),
               ("free dofs", fes.FreeDofs().NumSet()), ("dim", fes.dim),
               ("complex", fes.is_complex))
    if isinstance(fes, ngs.ProductSpace):
        details += (("components", len(fes.components)),)
    return Entry(name, "Space", "mdi-shape-outline", details)


def _gf(name, gf):
    fes = gf.space
    details = (("space", _space(fes), id(fes)), ("mesh", f"{fes.mesh.dim}D mesh", id(fes.mesh)),
               ("order", fes.globalorder), ("ndof", fes.ndof),
               ("dim", gf.dim), ("complex", fes.is_complex))
    if len(gf.components):
        details += (("components", len(gf.components)),)
    if len(gf.vecs) > 1:
        details += (("multidim", len(gf.vecs)),)
    parts = tuple((f".components[{i}]", ("components", i)) for i in range(len(gf.components)))
    return Entry(name, "GridFunction", "mdi-function-variant", details, drawable=True,
                 on_mesh=True, mesh_id=id(fes.mesh), parts=parts)


def _bf(name, bf):
    try:
        nze = bf.mat.nze
    except TypeError:
        nze = None
    details = (("space", _space(bf.space), id(bf.space)), ("ndof", bf.space.ndof),
               ("nonzeros", "not assembled" if nze is None else nze))
    return Entry(name, "BilinearForm", "mdi-matrix", details)


def _lf(name, lf):
    return Entry(name, "LinearForm", "mdi-vector-line",
                 (("space", _space(lf.space), id(lf.space)), ("ndof", lf.space.ndof)))


def _region(name, region):
    mask = region.Mask()
    vb = str(region.VB()).split(".")[-1]
    return Entry(name, "Region", "mdi-select-group",
                 (("type", vb), ("mesh", f"{region.mesh.dim}D mesh", id(region.mesh)),
                  ("regions", mask.NumSet()), ("of", len(mask))),
                 drawable=True, mesh_id=id(region.mesh),
                 target=vb == "VOL" or (vb == "BND" and region.mesh.dim == 3))


def _geometry(name, geo):
    shape = geo.shape if isinstance(geo, occ.OCCGeometry) else geo
    counts = (("solids", len(shape.solids)), ("faces", len(shape.faces)),
              ("edges", len(shape.edges)), ("vertices", len(shape.vertices)))
    return Entry(name, "Geometry", "mdi-cube-outline", counts, drawable=True)


def _cf(name, cf):
    return Entry(name, "Function", "mdi-function",
                 (("dim", cf.dim), ("complex", cf.is_complex)), on_mesh=True)


_TYPES = (
    (ngs.Mesh, _mesh),
    (ngs.FESpace, _fes),
    (ngs.GridFunction, _gf),
    (ngs.BilinearForm, _bf),
    (ngs.LinearForm, _lf),
    (ngs.Region, _region),
    ((occ.OCCGeometry, occ.TopoDS_Shape), _geometry),
    (ngs.CoefficientFunction, _cf),
)


@register_inspector
def inspect_ngsolve(name, obj):
    if any(getattr(m, name, None) is obj for m in (ngs, occ)):
        return None
    if isinstance(obj, ngs.comp.ProxyFunction):
        return None
    for types, fn in _TYPES:
        if isinstance(obj, types):
            return fn(name, obj)
    return None


_BYTES_PER_ELEMENT = 300   # netgen and ngsolve mesh with topology, measured


def _ram(obj):
    if isinstance(obj, ngs.Mesh):
        return obj.ne * _BYTES_PER_ELEMENT
    if isinstance(obj, ngs.GridFunction):
        return sum(v.size for v in obj.vecs) * (16 if obj.space.is_complex else 8)
    if isinstance(obj, (ngs.FESpace, ngs.BilinearForm, ngs.LinearForm)):
        return sum(m[1] for m in obj.__memory__)
    return None


def _vram(obj):
    """Bytes of the GPU buffers of the views of obj: the shared buffers of a
    mesh, the function values of a drawn function and its components."""
    from ngsolve_webgpu.cf import FunctionData
    from ngsolve_webgpu.mesh import shared_mesh_buffers
    from webgpu.utils import gpu_bytes, gpu_owners

    if isinstance(obj, ngs.Mesh):
        return gpu_bytes(*shared_mesh_buffers(obj))
    ids, parts = {id(obj)}, [obj]
    while parts:   # drawn components count as the function
        part = parts.pop()
        if isinstance(part, ngs.GridFunction):
            ids.update(id(c) for c in part.components)
            parts.extend(part.components)
    data = [d for d in gpu_owners() if isinstance(d, FunctionData) and id(d.cf) in ids]
    return gpu_bytes(*({k: v for k, v in vars(d).items() if k != "mesh_data"} for d in data))


@register_memory
def memory_ngsolve(obj):
    if not isinstance(obj, (ngs.Mesh, ngs.FESpace, ngs.GridFunction, ngs.BilinearForm,
                            ngs.LinearForm, ngs.CoefficientFunction)):
        return None
    return _ram(obj), _vram(obj)


def region_marks(mesh, kind, indices):
    """``{pick kind: region indices}`` that show the regions ``indices`` of
    ``kind``; a material of a 3D mesh also marks its boundary faces."""
    if mesh.dim == 2:
        return {"surface": indices} if kind == "material" else {"segment": indices}
    if kind == "boundary":
        return {"surface": indices}
    nrs = {i + 1 for i in indices}
    faces = tuple(i for i, fd in enumerate(mesh.ngmesh.FaceDescriptors())
                  if fd.domin in nrs or fd.domout in nrs)
    return {"volume": indices, "clipping": indices, "surface": faces}
