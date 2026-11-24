"""Layers whose renderers take ngsolve objects: facet values, field lines,
contact pairs."""

import traceback

import ngsolve as ngs
from ngapp.components import Observable, untracked
from ngsolve_webgpu.cf import FieldLines
from ngsolve_webgpu.contact import ContactPairs
from ngsolve_webgpu.facet_cf import FacetCFRenderer, FacetCFRenderer3D, FacetFunctionData
from webgpu.renderer import MultipleRenderer

from ..core.part import Binding, Layer, mark


class _SourceLayer(Layer):
    requires = ("mesh", "field", "colormap", "source")

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.field = view.part("field")
        self.colormap = view.part("colormap")
        self.source = view.part("source")

    def bind(self, r):
        def push():
            r.active = self.visible.value
            self.view.render()
        self.effect(push)


class Facet(_SourceLayer):
    """The field (or ``cf``) on the element boundaries; extracting it is
    expensive, so the renderer is made when first shown."""

    key = "facet"
    order = 51

    def __init__(self, cf=None, enabled=True):
        super().__init__()
        self.cf = cf
        self.enabled = enabled
        self.visible = self.observable("facet_visible", False)
        self.thickness = self.observable("facet_thickness", 0.008, converter=float)
        self._created = Observable(False, "facet_created")

    def attach(self, view):
        super().attach(view)

        def create_once():
            if self.visible.value:
                self._created.value = True
        self.effect(create_once)

    def applies(self):
        return self.enabled and self.context.dim in (2, 3)

    def build(self):
        self.context.revision.value
        data, clipping = self.field.data.value, self.view.clipping
        if data is None or not self._created.value:
            return []
        with untracked():
            r = self._create(data.mesh_data, clipping)
        return [] if r is None else [mark(r, "deformation")]

    def _create(self, mdata, clipping):
        source, colormap = self.source, self.colormap.colormap
        cf = self.cf if isinstance(self.cf, ngs.CoefficientFunction) else source.cf
        try:
            if self.context.dim == 2:
                # the deformation is baked in; its scale uniform switches it
                data = FacetFunctionData(mdata, cf, order=source.order,
                                         deformation_cf=source.deformation_cf)
                return FacetCFRenderer(data, colormap=colormap, clipping=clipping,
                                       thickness=self.thickness.value)
            return FacetCFRenderer3D(mdata, cf, order=source.order, colormap=colormap,
                                     clipping=clipping)
        except Exception as e:
            print(f"Warning: facet renderer creation failed: {e}")
            traceback.print_exc()
            return None

    def bind(self, r):
        super().bind(r)
        first = [True]

        def push_thickness():
            thickness = self.thickness.value
            if first[0]:
                first[0] = False
                return
            r.thickness = thickness
            r.set_needs_update()
            self.view.render()
        self.effect(push_thickness)

    def bindings(self):
        return [Binding("e", self.visible.toggle, "Toggle element boundaries", mode="s")]


class FieldLinesLayer(_SourceLayer):
    """Field lines of a vector field of the mesh dimension; the options apply
    on ``recalculate``."""

    key = "fieldlines"
    order = 55

    def __init__(self, num_lines=None, length=None, thickness=None):
        super().__init__()
        self.visible = self.observable("field_lines", False)
        self.num_lines = self.observable("fieldlines_num_lines", num_lines or 100, converter=int)
        self.length = self.observable("fieldlines_length", length or 0.5, converter=float)
        self.thickness = self.observable("fieldlines_thickness", thickness or 0.0015,
                                         converter=float)
        self.direction = self.observable("fieldlines_direction", 0, converter=int)

    def applies(self):
        return self.field.vectors.value is not None

    def options(self):
        return {"num_lines": self.num_lines.value, "length": self.length.value,
                "thickness": self.thickness.value, "direction": self.direction.value}

    def build(self):
        self.context.revision.value
        self.field.vectors.value
        clipping = self.view.clipping
        with untracked():
            return [FieldLines(self.source.vector_cf, self.source.region_or_mesh,
                               colormap=self.colormap.colormap, clipping=clipping,
                               **self.options())]

    def recalculate(self):
        r = self.renderer
        if r is not None:
            r.fieldline_options.update(self.options())
            r.set_needs_update()
            self.view.render()

    def bindings(self):
        return [Binding("f", self.visible.toggle, "Toggle field lines", mode="s")]


class Contact(Layer):
    """Contact pairs (one color per pair of a list)."""

    key = "contact"
    order = 52
    requires = ("mesh",)

    def __init__(self, contact, region_or_mesh):
        super().__init__()
        self.contact = contact
        self.region_or_mesh = region_or_mesh
        self.visible = self.observable("contact_enabled", True)

    def build(self):
        region = self.region_or_mesh
        if not isinstance(self.contact, list):
            return [ContactPairs(region, self.contact)]
        from ...region_colors import get_random_colors

        colors = get_random_colors(len(self.contact))
        return [MultipleRenderer([ContactPairs(region, c, color=col)
                                  for c, col in zip(self.contact, colors)])]

    def bind(self, r):
        def push():
            r.active = self.visible.value
            self.view.render()
        self.effect(push)
