"""MeshContext: the mesh data of a view, shared by its mesh layers."""

from ngapp.components import Observable, computed, untracked

from .part import Part


class MeshContext(Part):
    """``make_data(el2d_bitarray=None, el3d_bitarray=None)`` returns a
    ``MeshData``; the unfiltered one is kept, filtered ones are made while
    element masks are set. Layers rebuild when ``data`` or ``revision``
    change."""

    key = "mesh"

    def __init__(self, make_data, edge_names=(), curve_order=1):
        super().__init__()
        self._make = make_data
        self.base_data = make_data()
        self.edge_names = list(edge_names)
        self.masks = Observable((None, None), "element_masks")
        self.revision = Observable(0, "mesh_revision")
        self.curve_order = Observable(curve_order, "curve_order")
        self.data = computed(self._data, "mesh_data")

    def _data(self):
        el2d, el3d = self.masks.value
        if el2d is None and el3d is None:
            return self.base_data
        return self._make(el2d_bitarray=el2d, el3d_bitarray=el3d)

    @property
    def dim(self):
        return self.base_data.dim

    def changed(self):
        """The mesh buffers are stale (curving, subdivision): rebuild."""
        with untracked():
            self.data.value.set_needs_update()
            self.revision.value = self.revision.value + 1
