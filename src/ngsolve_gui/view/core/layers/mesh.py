"""Layers drawing the mesh of the view's MeshContext."""

from ngapp.components import Observable, untracked
from ngsolve_webgpu.mesh import (
    MeshElements2d,
    MeshElements3d,
    MeshIdentifications,
    MeshSegments,
    MeshWireframe2d,
)

from ..part import Binding, Layer, Tool


class MeshLayer(Layer):
    """One renderer of ``create(data, clipping)``, shown while ``visible``."""

    requires = ("mesh",)
    visible_key = ""
    visible_default = True
    show_key = None          # key in the "Show" mode
    label = ""

    def __init__(self, visible=None):
        super().__init__()
        self.visible = self.observable(
            self.visible_key, self.visible_default if visible is None else visible)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")

    def build(self):
        self.context.revision.value
        return [self.create(self.context.data.value, self.view.clipping)]

    def create(self, data, clipping):
        raise NotImplementedError

    def bind(self, r):
        def push():
            r.active = self.visible.value
            self.view.render()
        self.effect(push)

    def bindings(self):
        if self.show_key is None:
            return []
        return [Binding(self.show_key, self.visible.toggle, f"Toggle {self.label}", mode="s")]


class Wireframe(MeshLayer):
    key = "wireframe"
    order = 20
    visible_key = "wireframe_visible"
    show_key = "w"
    label = "wireframe"

    def create(self, data, clipping):
        return MeshWireframe2d(data, clipping=clipping)

    def tools(self):
        return [Tool(20, lambda: self.view.tool_button(
            "mdi-grid", "Wireframe  ·  w", self.visible.toggle, active=self.visible))]

    def bindings(self):
        return [Binding("w", self.visible.toggle, "Toggle wireframe"), *super().bindings()]


class Elements2d(MeshLayer):
    key = "elements2d"
    order = 10
    pick_kind = "surface"
    visible_key = "elements2d_visible"
    show_key = "2"
    label = "elements 2D"

    def create(self, data, clipping):
        return MeshElements2d(data, clipping=clipping)


class Segments(MeshLayer):
    """Segments with colors per edge descriptor name."""

    key = "segments"
    order = 40
    visible_key = "elements1d_visible"
    visible_default = False
    show_key = "1"
    label = "elements 1D"

    def __init__(self):
        super().__init__()
        self.edge_colors = self.observable("edge_colors", {})

    def _colors(self):
        colors = self.edge_colors.value
        if not colors:
            return None
        return [colors.get(name, [0, 0, 0, 255]) for name in self.context.edge_names]

    def create(self, data, clipping):
        return MeshSegments(data, clipping=clipping, colors=untracked(self._colors))

    def bind(self, r):
        super().bind(r)
        first = [True]

        def push_colors():
            colors = self._colors()
            if first[0]:
                first[0] = False
                return
            r._user_colors = colors
            r.set_needs_update()
            self.view.render()
        self.effect(push_colors)


class Identifications(MeshLayer):
    key = "identifications"
    order = 45
    visible_key = "identifications_visible"
    visible_default = False
    show_key = "i"
    label = "identifications"

    def create(self, data, clipping):
        return MeshIdentifications(data, clipping=clipping)


class Elements3d(MeshLayer):
    """Volume elements, created when first shown."""

    key = "elements3d"
    order = 30
    pick_kind = "volume"
    visible_key = "elements3d_visible"
    visible_default = False
    show_key = "3"
    label = "elements 3D"
    SUBDIVISION_MAX = 3

    def __init__(self):
        super().__init__()
        self.shrink = self.observable("shrink", 1.0, converter=float)
        self.subdivision = self.observable("elements3d_subdivision", -1, converter=int)
        self._created = Observable(False, "elements3d_created")

    def attach(self, view):
        super().attach(view)
        self.subdivision.value = view.defaults.ref(
            "default_elements3d_subdivision", -1, int).value

        def create_once():
            if self.visible.value:
                self._created.value = True
        self.effect(create_once)

    def applies(self):
        return self.context.dim == 3

    def build(self):
        if not self._created.value:
            return []
        return super().build()

    def create(self, data, clipping):
        return MeshElements3d(data, clipping=clipping)

    def bind(self, r):
        super().bind(r)

        def push_shrink():
            r.shrink = self.shrink.value
            self.view.render()

        def push_subdivision():
            v = self.subdivision.value
            clamped = max(-1, min(self.SUBDIVISION_MAX, v))
            if clamped != v:
                self.subdivision.value = clamped
                return
            r.subdivision = None if v < 0 else v + 1
            self.view.render()
        self.effect(push_shrink)
        self.effect(push_subdivision)


class _Tint(MeshSegments):
    """Lines blended over the scene (transparent pass)."""

    def get_export_descriptor(self, options, buffer_registry):
        desc = super().get_export_descriptor(options, buffer_registry)
        desc.pass_type, desc.depth_write, desc.blend = "transparent", False, "premultiplied"
        return desc


class BoundaryMarks(Layer):
    """Marked boundaries of a 2D mesh as thick lines, see ``Picking.mark_regions``."""

    key = "boundary_marks"
    order = 45
    requires = ("mesh",)
    mark_kind = "segment"
    color = (1.0, 0.5, 0.0, 0.6)

    def __init__(self):
        super().__init__()
        self._marked = ()

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")

    def applies(self):
        return self.context.dim == 2

    def _colors(self):
        n = len(self.context.base_data.boundary_names)
        return [self.color if i in self._marked else (0, 0, 0, 0) for i in range(n)]

    def build(self):
        self.context.revision.value
        r = _Tint(self.context.data.value, clipping=self.view.clipping,
                  colors=untracked(self._colors))
        r.thickness = 0.012
        return [r]

    def mark(self, indices):
        self._marked = tuple(indices)
        if self.renderer is not None:
            self.renderer.set_colors(self._colors())


class Edges(Layer):
    """The 1D elements as lines of a given thickness (geometry edges)."""

    key = "edges"
    order = 25
    requires = ("mesh",)

    def __init__(self, thickness=None):
        super().__init__()
        self.thickness = thickness

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")

    def build(self):
        self.context.revision.value
        r = MeshSegments(self.context.data.value, clipping=self.view.clipping)
        if self.thickness is not None:
            r.thickness = float(self.thickness)
        return [r]
