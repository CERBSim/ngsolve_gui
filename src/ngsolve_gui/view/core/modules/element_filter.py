"""Element filters: named masks over the elements, combined with AND."""

from collections import Counter

import numpy as np

from ..part import Part


class ElementFilter(Part):
    """Base masks (``el2d``, ``el3d``, e.g. from DrawBadElements) and named
    masks of kind ``"vol"`` or ``"surf"`` over all elements of the mesh;
    drawn through the element bits of the region visibility buffer."""

    key = "element_filter"
    requires = ("mesh", "regions")

    def __init__(self, el2d=None, el3d=None):
        super().__init__()
        self._base = (el2d, el3d)
        self._filters = {}

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.visibility = view.part("regions").visibility
        self._apply()

    def set(self, name, kind, mask):
        """Set (mask) or clear (None) a named filter."""
        if mask is None:
            if self._filters.pop(name, None) is None:
                return
        else:
            self._filters[name] = (kind, mask)
        self._apply()

    def _apply(self):
        surf, vol = self._base
        for kind, mask in self._filters.values():
            if kind == "vol":
                vol = mask if vol is None else (vol & mask)
            else:
                surf = mask if surf is None else (surf & mask)
        counts = self.visibility.element_counts
        self.visibility.set_element_masks(*self.context.base_data.drawn_masks(surf, vol))
        if counts != self.visibility.element_counts and self.view.draws:
            # a new buffer: the renderers bind it when rebuilt
            self.context.rebuild()
        else:
            self.view.render()

    def element_types(self):
        """{type name: count} of the volume elements (empty for 2D)."""
        if self.context.dim != 3:
            return {}
        return {str(t): n for t, n in Counter(self.context.base_data.element_types()).items()}

    def show_types(self, visible):
        """Show only the volume elements of the given type names."""
        visible = set(visible)
        types = self.context.base_data.element_types()
        mask = None if visible >= set(types) else np.isin(types, list(visible))
        self.set("eltype", "vol", mask)
