"""Vector glyphs and line integral convolution of a vector field."""

from ngapp.components import untracked
from ngsolve_webgpu.lic import ClippingLIC, SurfaceLIC
from ngsolve_webgpu.vectors import ClippingVectors, SurfaceVectors

from ..part import Binding, Layer, Part, mark


def _positive_int(value):
    value = int(float(value))
    if value < 1:
        raise ValueError(value)
    return value


class VectorStyle(Part):
    """Grid size and scale shared by the vector layers."""

    key = "vector_style"
    requires = ("field",)
    LAYERS = ("surface_vectors", "clip_vectors")

    def __init__(self):
        super().__init__()
        self.grid_size = self.observable("vector_grid_size", 20, converter=_positive_int)
        self.scale = self.observable("vector_scale", 1.0, converter=float)
        self.scale_by_value = self.observable("vector_scale_by_value", False)

    def attach(self, view):
        super().attach(view)
        self.grid_size.value = int(view.defaults.get("default_vector_grid_size", 20))

    def applies(self):
        return any(self.view.part(k) is not None and self.view.part(k).applies()
                   for k in self.LAYERS)

    def change_density(self, factor):
        self.grid_size.value = max(10, int(self.grid_size.value * factor))

    def bindings(self):
        return [
            Binding("+", lambda: self.change_density(1.25), "Increase vector density", mode="s"),
            Binding("-", lambda: self.change_density(0.8), "Decrease vector density", mode="s"),
        ]


class _FieldLayer(Layer):
    requires = ("mesh", "field", "colormap")
    visible_key = ""

    def __init__(self, visible=False):
        super().__init__()
        self.visible = self.observable(self.visible_key, visible)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.field = view.part("field")
        self.colormap = view.part("colormap")

    def build(self):
        self.context.revision.value
        clipping = self.view.clipping
        data = self.data()
        if data is None:
            return []
        with untracked():
            return [self.create(data, clipping, self.colormap.colormap)]

    def data(self):
        return self.field.data.value

    def bind(self, r):
        def push():
            r.active = self.visible.value
            self.view.render()
        self.effect(push)


class _Vectors(_FieldLayer):
    requires = ("mesh", "field", "colormap", "vector_style")

    def attach(self, view):
        super().attach(view)
        self.style = view.part("vector_style")

    def create(self, data, clipping, colormap):
        style = self.style
        r = self.renderer_class(data, clipping=clipping, colormap=colormap,
                                grid_size=style.grid_size.value,
                                scale_by_value=style.scale_by_value.value)
        r.user_scale = style.scale.value
        return mark(r, "complex")

    def bind(self, r):
        super().bind(r)
        style = self.style
        first = [True]

        def push_style():
            grid_size, scale = style.grid_size.value, style.scale.value
            by_value = style.scale_by_value.value
            if first[0]:
                first[0] = False
                return
            r.set_grid_size(grid_size)
            r.user_scale = scale
            r.scale_by_value = by_value
            r.set_needs_update()
            self.view.render()
        self.effect(push_style)


class SurfaceVectorsLayer(_Vectors):
    key = "surface_vectors"
    order = 54
    visible_key = "surface_vectors"
    renderer_class = SurfaceVectors

    def applies(self):
        return self.field.vectors.value is not None

    def data(self):
        return self.field.vectors.value

    def bindings(self):
        return [Binding("v", self.visible.toggle, "Toggle surface vectors", mode="s")]


class ClipVectorsLayer(_Vectors):
    key = "clip_vectors"
    order = 53
    visible_key = "clipping_vectors"
    renderer_class = ClippingVectors

    def __init__(self, visible=False, enabled=True):
        super().__init__(visible)
        self.enabled = enabled

    def applies(self):
        return self.enabled and self.context.dim == 3 and self.field.dim == 3

    def bindings(self):
        return [Binding("c", self.visible.toggle, "Toggle clipping vectors", mode="s")]


class Lic(_FieldLayer):
    """On the surface of a 2D mesh (replacing the surface field) or on the
    clipping plane of a 3D mesh."""

    key = "lic"
    order = 50
    visible_key = "lic_visible"

    def __init__(self, visible=False, enabled=True):
        super().__init__(visible)
        self.enabled = enabled
        self.kernel_length = self.observable("lic_kernel_length", 30, converter=int)
        self.oriented = self.observable("lic_oriented", False)
        self.thickness = self.observable("lic_thickness", 2, converter=int)
        self.contrast = self.observable("lic_contrast", 1.0, converter=float)
        self.supersample = self.observable("lic_supersample", False)

    def attach(self, view):
        super().attach(view)
        regions = view.part("regions")
        if regions is not None:
            regions.listeners.append(lambda: untracked(self._refresh))

    def _refresh(self):
        r = self.renderer
        if r is not None:
            r._refresh()

    @property
    def on_surface(self):
        return self.context.dim == 2

    def applies(self):
        if self.on_surface:
            return self.field.vectors.value is not None
        return self.enabled and self.context.dim == 3 and self.field.dim == 3

    def data(self):
        return self.field.vectors.value if self.on_surface else self.field.data.value

    def create(self, data, clipping, colormap):
        cls = SurfaceLIC if self.on_surface else ClippingLIC
        r = cls(data, clipping=clipping, colormap=colormap,
                kernel_length=self.kernel_length.value, oriented=self.oriented.value,
                thickness=self.thickness.value, contrast=self.contrast.value,
                supersample=2 if self.supersample.value else 1)
        return mark(r, "component", "complex")

    def pickables(self):
        return [(r, "surface") for r in self.renderers.value] if self.on_surface else []

    def suppresses(self, key):
        return key == "surface" and self.on_surface and self.visible.value and self.applies()

    def bind(self, r):
        super().bind(r)
        for obs, setter in ((self.kernel_length, r.set_kernel_length),
                            (self.oriented, r.set_oriented),
                            (self.thickness, r.set_thickness),
                            (self.contrast, r.set_contrast),
                            (self.supersample, lambda v: r.set_supersample(2 if v else 1))):
            self.effect(self._pusher(obs, setter))

    def _pusher(self, obs, setter):
        first = [True]

        def push():
            value = obs.value
            if first[0]:
                first[0] = False
                return
            setter(value)
            self.view.render()
        return push

    def bindings(self):
        out = [Binding("l", self.visible.toggle, "Toggle LIC", mode="s")]
        if not self.on_surface:
            out.append(Binding("l", self.visible.toggle, "Toggle LIC", mode="c"))
        return out
