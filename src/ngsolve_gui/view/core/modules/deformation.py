"""Deformation of the mesh by a displacement field."""

from ngapp.components import Observable, batch

from ..part import Binding, Part


class Deformation(Part):
    """``data`` is the FunctionData of the 3D displacement, None without
    deformation; a source sets it with ``set_data`` together with the field.
    The mesh data of the view is deformed by ``scale * scale2`` while
    enabled."""

    key = "deformation"
    requires = ("mesh",)

    def __init__(self):
        super().__init__()
        self.data = Observable(None, "deformation_data")
        self.enabled = self.observable("deformation_enabled", False)
        self.scale = self.observable("deformation_scale", 1.0, converter=float)
        self.scale2 = self.observable("deformation_scale2", 1.0, converter=float)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.effect(self._push)

    def applies(self):
        return self.data.value is not None

    def factor(self):
        return self.scale.value * self.scale2.value if self.enabled.value else 0.0

    def set_data(self, data):
        """Renderers built afterwards read the new displacement."""
        self.context.base_data.deformation_data = data
        self.data.value = data

    def _push(self):
        data = self.data.value
        self.context.base_data.deformation_scale = self.factor() if data is not None else 0.0
        for r in self.view.with_role("deformation"):
            r.set_needs_update()
        self.view.render()

    def step(self, factor):
        self.scale.value = self.scale.value * factor

    def reset(self):
        with batch():
            self.scale.value = 1.0
            self.scale2.value = 1.0

    def bindings(self):
        return [
            Binding("d", self.enabled.toggle, "Toggle deformation", mode="d"),
            Binding("+", lambda: self.step(1.25), "Increase scale", mode="d"),
            Binding("-", lambda: self.step(0.8), "Decrease scale", mode="d"),
            Binding("0", self.reset, "Reset scale to 1.0", mode="d"),
        ]
