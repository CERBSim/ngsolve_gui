"""Layers drawing the view's field with its colormap."""

from ngsolve_webgpu.isolines import ClippingIsolineRenderer, IsolineRenderer

from ..part import Binding, Layer, mark


class FieldLayer(Layer):
    """One renderer of the field, shown while ``visible`` and not hidden by
    another part (``suppresses``)."""

    requires = ("mesh", "field", "colormap")
    visible_key = ""
    roles = ("component", "complex")

    def __init__(self, visible=None, enabled=True):
        super().__init__()
        self.visible = self.observable(self.visible_key, True if visible is None else visible)
        self.enabled = enabled

    def applies(self):
        return self.enabled

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.field = view.part("field")
        self.colormap = view.part("colormap")

    def build(self):
        self.context.revision.value
        data = self.field.data.value
        if data is None:
            return []
        return [mark(self.create(data, self.view.clipping, self.colormap.colormap), *self.roles)]

    def bind(self, r):
        def push():
            hidden = any(p.suppresses(self.key) for p in self.view.parts)
            r.active = self.visible.value and not hidden
            self.view.render()
        self.effect(push)


class Surface(FieldLayer):
    """The field on the surface elements (the 2D elements of a 2D mesh)."""

    key = "surface"
    order = 10
    pick_kind = "surface"
    visible_key = "elements2d_visible"

    def create(self, data, clipping, colormap):
        return IsolineRenderer(data, n_lines=0, show_field=True, clipping=clipping, colormap=colormap)

    def bindings(self):
        return [Binding("s", self.visible.toggle, "Toggle surface", mode="s")]


class ClipField(FieldLayer):
    """The field on the clipping plane through the volume elements."""

    key = "clipfield"
    order = 5
    pick_kind = "clipping"
    visible_key = "clipping_visible"
    roles = ("component", "complex", "deformation")

    def applies(self):
        return self.enabled and self.context.dim == 3

    def create(self, data, clipping, colormap):
        return ClippingIsolineRenderer(data, clipping=clipping, n_lines=0, show_field=True,
                                       colormap=colormap)

    def bindings(self):
        return [Binding("f", self.visible.toggle, "Toggle clipping function", mode="c")]
