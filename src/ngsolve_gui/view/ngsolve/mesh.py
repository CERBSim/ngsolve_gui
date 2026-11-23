"""Mesh context, curving and element quality for ngsolve meshes."""

import numpy as np
import ngsolve as ngs
from ngapp.components import Observable
from ngsolve_webgpu.mesh import MeshData

from ..core.context import MeshContext
from ..core.part import Part


def mesh_context(region_or_mesh):
    mesh = region_or_mesh.mesh if isinstance(region_or_mesh, ngs.Region) else region_or_mesh
    return MeshContext(
        lambda **masks: MeshData(region_or_mesh, **masks),
        edge_names=[ed.name for ed in mesh.ngmesh.EdgeDescriptors()],
        curve_order=mesh.GetCurveOrder())


class Curvature(Part):
    """Curves the mesh (``mesh.Curve`` changes it for every view) when the
    order is changed; starts from the order the mesh has."""

    key = "curvature"
    requires = ("mesh",)

    def __init__(self, mesh):
        super().__init__()
        self.mesh = mesh
        order = mesh.GetCurveOrder()
        self.enabled = Observable(order > 1, "mesh_curvature_enabled")
        self.order = Observable(max(2, order), "mesh_curvature_order", converter=int)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.effect(self._push)

    def _push(self):
        order = int(self.order.value) if self.enabled.value else 1
        if order == self.mesh.GetCurveOrder():
            return
        self.mesh.Curve(order)
        self.context.curve_order.value = order
        self.context.changed()


def element_quality(mesh):
    """Per volume element the maximum of Norm(J) * Norm(J^-1) (the condition
    number of the Jacobian; about dim for good elements)."""
    dim = mesh.dim
    jac = ngs.specialcf.JacobianMatrix(dim, dim)
    cf = ngs.Norm(jac) * ngs.Norm(ngs.Inv(jac))
    intrule = ngs.IntegrationRule(ngs.ET.TET if dim == 3 else ngs.ET.TRIG, 4)
    pnts = mesh.MapToAllElements(intrule, ngs.VOL).flatten()
    return np.max(cf(pnts).reshape((-1, len(intrule))), axis=1)
