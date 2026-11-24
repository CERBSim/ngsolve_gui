"""Presets: the parts of a mesh and a function view from the Draw arguments.
``configure_*`` applies the arguments that win over the saved state."""

import ngsolve as ngs

from ..core.layers.field import ClipField, Surface
from ..core.layers.mesh import Edges, Elements2d, Elements3d, Identifications, Segments, Wireframe
from ..core.layers.numbers import Numbers
from ..core.layers.vectors import ClipVectorsLayer, Lic, SurfaceVectorsLayer, VectorStyle
from ..core.modules.colormap import Colormap
from ..core.modules.complex import Complex
from ..core.modules.deformation import Deformation
from ..core.modules.element_filter import ElementFilter
from ..core.modules.field import Field
from ..core.modules.regions import Regions
from ..core.modules.subdivision import Subdivision, by_curve_order
from .field import FieldSource
from .layers import Contact, Facet, FieldLinesLayer
from .mesh import Curvature, mesh_context

FUNCTION_SUBDIVISION_MAX = 40


def mesh_of(region_or_mesh):
    return region_or_mesh.mesh if isinstance(region_or_mesh, ngs.Region) else region_or_mesh


def mesh_view(region_or_mesh, undo=None, **draw):
    mesh = mesh_of(region_or_mesh)
    return [
        mesh_context(region_or_mesh),
        Curvature(mesh),
        Subdivision(draw.get("subdivision"), auto=by_curve_order),
        ElementFilter(draw.get("el2d_bitarray"), draw.get("el3d_bitarray")),
        Regions(undo=undo),
        Wireframe(), Elements2d(), Segments(), Identifications(), Elements3d(),
        Numbers(mesh.dim),
    ]


def _grid_size(value):
    return None if isinstance(value, bool) else value


def function_view(cf, region_or_mesh, undo=None, **draw):
    mesh = mesh_of(region_or_mesh)
    draw_vol = bool(draw.get("draw_vol", True))
    edges = draw.get("edges", False)
    parts = [
        mesh_context(region_or_mesh),
        Subdivision(draw.get("subdivision"), max=FUNCTION_SUBDIVISION_MAX),
        Regions(undo=undo),
        Field(), Deformation(), Complex(), Colormap(),
        FieldSource(cf, region_or_mesh, order=draw.get("order"),
                    labels=draw.get("component_labels"),
                    deformation=draw.get("deformation"),
                    deformation_order=draw.get("deformation_order")),
        VectorStyle(),
        Wireframe(visible=draw.get("wireframe")),
        Surface(enabled=bool(draw.get("draw_surf", True))),
        ClipField(enabled=draw_vol),
        Lic(enabled=draw_vol),
        Facet(draw.get("facet"), enabled=draw_vol),
        ClipVectorsLayer(enabled=draw_vol),
        SurfaceVectorsLayer(),
        FieldLinesLayer(draw.get("fieldlines_num_lines"), draw.get("fieldlines_length"),
                        draw.get("fieldlines_thickness")),
    ]
    if draw.get("contact") is not None:
        parts.append(Contact(draw["contact"], region_or_mesh))
    if edges:
        parts.append(Edges(None if isinstance(edges, bool) else edges))
    parts.append(Numbers(mesh.dim))
    return parts


def configure_function(view, draw):
    part = view.part
    if "deformation" in draw and part("deformation").applies():
        part("deformation").enabled.value = True
    if "clipping_function" in draw:
        part("clipfield").visible.value = bool(draw["clipping_function"])
    if draw.get("facet") is not None:
        part("facet").visible.value = bool(draw["facet"])
    for key, layer in (("clipping_vectors", "clip_vectors"), ("surface_vectors", "surface_vectors"),
                       ("field_lines", "fieldlines"), ("lic", "lic")):
        if draw.get(key):
            part(layer).visible.value = True
    grid_size = _grid_size(draw.get("clipping_vectors")) or _grid_size(draw.get("surface_vectors"))
    if grid_size:
        part("vector_style").grid_size.value = grid_size
    colormap = part("colormap")
    if any(k in draw for k in ("min", "max", "autoscale")):
        colormap.autoscale.value = draw.get("autoscale", not ("min" in draw or "max" in draw))
    if "min" in draw:
        colormap.min.value = draw["min"]
    if "max" in draw:
        colormap.max.value = draw["max"]
    if "discrete_colormap" in draw:
        colormap.discrete.value = bool(draw["discrete_colormap"])
