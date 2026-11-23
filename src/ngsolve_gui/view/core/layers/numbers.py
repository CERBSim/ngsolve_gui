"""Index labels on mesh entities."""

from ngsolve_webgpu import EntityNumbers

from ..part import Binding, Layer

_KEYS = {
    "vertices": ("v", "Vertex numbers"),
    "edges": ("e", "Edge numbers"),
    "facets": ("f", "Facet numbers"),
    "surface_elements": ("s", "Surface el. numbers"),
    "volume_elements": ("3", "Volume el. numbers"),
}


def entities(dim):
    out = ["vertices", "edges", "facets", "segments", "surface_elements"]
    if dim == 3:
        out.append("volume_elements")
    out += ["surface_indices", "segment_indices"]
    if dim == 3:
        out.append("volume_indices")
    return out


class Numbers(Layer):
    """One label renderer per entity; ``dim`` decides the entities (and so
    the state keys)."""

    key = "numbers"
    order = 60
    requires = ("mesh",)

    def __init__(self, dim):
        super().__init__()
        self.entities = entities(dim)
        self.visible = {e: self.observable(f"{e}_numbers_visible", False) for e in self.entities}
        self.one_based = self.observable("numbers_one_based", False)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")

    def build(self):
        self.context.revision.value
        data, clipping = self.context.data.value, self.view.clipping
        return [EntityNumbers(data, entity=e, clipping=clipping) for e in self.entities]

    def bind(self, r):
        visible = self.visible[r.entity]

        def push():
            r.active = visible.value
            self.view.render()

        def push_base():
            zero_based = not self.one_based.value
            if r.zero_based != zero_based:
                r.zero_based = zero_based
                r.set_needs_update()
                self.view.render()
        self.effect(push)
        self.effect(push_base)

    def bindings(self):
        return [Binding(key, self.visible[e].toggle, desc, mode="n")
                for e, (key, desc) in _KEYS.items() if e in self.visible]
