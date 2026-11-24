"""Field: the FunctionData a view shows and the component shown."""

from ngapp.components import Observable, batch

from ..part import Part, has_role


class Field(Part):
    """``data`` is set by a source (``set_data``); layers drawing the field
    build from it. ``vectors`` is the field as 3D vectors if it is a vector
    field of the mesh dimension, else None. ``component`` -1 is the norm."""

    key = "field"
    requires = ("mesh",)

    def __init__(self):
        super().__init__()
        self.data = Observable(None, "field_data")
        self.vectors = Observable(None, "field_vectors")
        self.component = Observable(-1, "field_component")

    def attach(self, view):
        super().attach(view)
        self.effect(self._push_component)

    def set_data(self, data, vectors=None):
        with batch():
            self.vectors.value = vectors
            self.data.value = data

    @property
    def dim(self):
        data = self.data.value
        return data.num_components if data is not None else 0

    @property
    def is_complex(self):
        data = self.data.value
        return data is not None and data.is_complex

    @property
    def labels(self):
        data = self.data.value
        return data.component_labels if data is not None else []

    def prepare(self, renderers):
        component = self.component.value
        if component != -1:
            for r in renderers:
                if has_role(r, "component"):
                    r.gpu_objects.settings.component = component

    def _push_component(self):
        component = self.component.value
        for r in self.view.with_role("component"):
            r.set_component(component)
        self.view.render()

    def evaluate(self, point):
        """Value at a world point of the undeformed mesh, None outside."""
        data = self.data.value
        return data.evaluate(point) if data is not None else None
