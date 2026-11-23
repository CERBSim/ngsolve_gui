"""Generic layers."""

from ngapp.components import Observable

from ..part import Layer


class Raw(Layer):
    """Renderers given from outside, with the ones that can be picked."""

    key = "raw"

    def __init__(self, key="raw", order=50):
        self.key = key
        self.order = order
        self._given = Observable(((), ()), f"{key}_renderers")
        super().__init__()

    def set(self, renderers, pickables=()):
        self._given.value = (tuple(renderers), tuple(pickables))

    def build(self):
        return self._given.value[0]

    def pickables(self):
        return list(self._given.value[1])
