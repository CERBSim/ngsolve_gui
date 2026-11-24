"""MeshContext: the mesh data of a view, shared by its mesh layers."""

from ngapp.components import Observable, untracked

from .part import Part


class MeshContext(Part):
    """The ``MeshData`` of a view (``base_data``; ``data`` for the layers).
    Layers rebuild when ``data`` or ``revision`` change."""

    key = "mesh"

    def __init__(self, data, edge_names=(), curve_order=1):
        super().__init__()
        self.base_data = data
        self.edge_names = list(edge_names)
        self.revision = Observable(0, "mesh_revision")
        self.curve_order = Observable(curve_order, "curve_order")
        self.data = Observable(data, "mesh_data")

    @property
    def dim(self):
        return self.base_data.dim

    def changed(self):
        """The mesh buffers are stale (curving, subdivision): rebuild."""
        with untracked():
            self.data.value.set_needs_update()
        self.rebuild()

    def rebuild(self):
        """New renderers for the layers on the same buffers."""
        with untracked():
            self.revision.value = self.revision.value + 1
