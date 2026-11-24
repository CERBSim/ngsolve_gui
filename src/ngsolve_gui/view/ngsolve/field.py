"""FieldSource: a CoefficientFunction on a mesh as the field (and the
deformation) of a view."""

import ngsolve as ngs
from ngapp.components import batch
from ngsolve_webgpu.cf import FunctionData
from ngsolve_webgpu.mesh import MeshData

from ..core.part import Part


def default_order(cf):
    if isinstance(cf, ngs.GridFunction):
        return min(2, cf.space.globalorder)
    return 2


def resolve_deformation(deform, cf, mesh_dim):
    """The ``deformation`` Draw argument as a 3D displacement CF or None;
    True deforms by the field itself."""
    if deform is None or deform is False:
        return None
    if deform is True:
        deform = cf
    if not isinstance(deform, ngs.CoefficientFunction):
        print(f"Warning: ignoring deformation of type {type(deform).__name__}")
        return None
    # FacetFESpace functions can't be evaluated inside elements
    if isinstance(deform, ngs.GridFunction) and isinstance(deform.space, ngs.FacetFESpace):
        return None
    if deform.dim == 3:
        return deform
    if deform.dim == 2:
        return ngs.CF((deform[0], deform[1], 0))
    if deform.dim == 1 and mesh_dim < 3:
        return ngs.CF((0, 0, deform))
    print(f"Warning: cannot use a {deform.dim}-dimensional field as deformation "
          f"on a {mesh_dim}d mesh")
    return None


class FieldSource(Part):
    """Sets the data of the ``field`` and ``deformation`` parts from a CF.
    Without a ``deformation`` argument a scalar field on a 1D or 2D mesh
    deforms the mesh by its value."""

    key = "source"
    requires = ("mesh", "field")

    def __init__(self, cf, region_or_mesh, **options):
        super().__init__()
        self.region_or_mesh = region_or_mesh
        self.mesh = region_or_mesh.mesh if isinstance(region_or_mesh, ngs.Region) else region_or_mesh
        self._initial = (cf, options)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        cf, options = self._initial
        self.set_cf(cf, **options)

    def set_cf(self, cf, order=None, labels=None, deformation=None,
               deformation_order=None, **_):
        """Show another CF (the retarget of the view)."""
        if labels is not None and len(labels) != cf.dim:
            print(f"Warning: ignoring {len(labels)} component labels for a {cf.dim}-component field")
            labels = None
        self.cf = cf
        self.order = order or default_order(cf)
        data = FunctionData(self.context.base_data, cf, order=self.order, component_labels=labels)
        if deformation is None and cf.dim == 1 and self.mesh.dim < 3:
            deformation = True
        self.vector_cf = None
        vectors = None
        if cf.dim == self.mesh.dim and cf.dim > 1:
            self.vector_cf = cf if cf.dim == 3 else ngs.CF((cf[0], cf[1], 0))
            vectors = data if cf.dim == 3 else FunctionData(
                self.context.base_data, self.vector_cf, order=self.order)
        deform = resolve_deformation(deformation, cf, self.mesh.dim)
        self.deformation_cf = deform
        deform_data = None
        if deform is not None:
            deform_data = FunctionData(MeshData(self.region_or_mesh), deform,
                                       order=deformation_order or self.order)
        with batch():
            part = self.view.part("deformation")
            if part is not None:
                part.set_data(deform_data)
            self.view.part("field").set_data(data, vectors)
            if self.view.draws:
                self.context.changed()
