"""Subdivision of the curved mesh elements."""

from ngapp.components import untracked

from ..part import Part


def by_curve_order(order):
    """Levels for a mesh curved to ``order``."""
    if order > 3:
        return (order + 2) // 3 + 1
    return 3 if order > 1 else 1


class Subdivision(Part):
    """``subdivision`` -1 is automatic (``auto(curve_order)``, or left to the
    mesh data without ``auto``), n >= 0 means n + 1 levels. The buffers are
    shared by all views of a mesh and only grow."""

    key = "subdivision"
    requires = ("mesh",)
    MAX = 5

    def __init__(self, default=None, auto=None):
        super().__init__()
        self._default = default
        self._auto = auto
        self.value = self.observable("subdivision", -1, converter=int)
        self._pushed = (None, None)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        default = self._default
        if default is None:
            default = view.defaults.ref("default_subdivision", -1, int).value
        self.value.value = default
        self.effect(self._push)

    def levels(self):
        v = self.value.value
        if v >= 0:
            return v + 1
        if self._auto is None:
            return None
        return self._auto(self.context.curve_order.value)

    def _push(self):
        v = self.value.value
        clamped = max(-1, min(self.MAX, v))
        if clamped != v:
            self.value.value = clamped
            return
        data = self.context.data.value
        levels = self.levels()
        before = data.subdivision
        data.subdivision = levels
        last, self._pushed = self._pushed, (data, levels)
        if last[0] is data and data.subdivision != before:
            self.context.changed()
