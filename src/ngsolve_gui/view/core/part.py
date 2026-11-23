"""Part: a unit of a viewport with its own state, tools, bindings and
overlays. Layer: a part that produces renderers."""

from dataclasses import dataclass
from typing import Callable

from ngapp.components import Observable, computed, effect


@dataclass
class Binding:
    key: str
    action: Callable
    desc: str
    mode: str | None = None        # trigger of the mode, None: flat
    group: str = "General"         # help group of a flat binding


@dataclass
class Tool:
    """A button of the tool dock; tools of one group sit between separators."""
    order: int
    build: Callable                 # () -> component
    group: int = 0


class Part:
    key = ""
    requires = ()

    def __init__(self):
        self.view = None
        self._state = {}
        self._effects = []

    def observable(self, name, default, **kwargs):
        """An observable whose value is part of the saved state under name."""
        obs = Observable(default, name, **kwargs)
        self._state[name] = obs
        return obs

    def state(self):
        return {name: obs.value for name, obs in self._state.items()}

    def load_state(self, values):
        for name, obs in self._state.items():
            if name in values:
                try:
                    obs.value = values[name]
                except Exception:
                    pass

    def attach(self, view):
        self.view = view

    def effect(self, fn):
        """An effect that lives as long as the part."""
        self._effects.append(effect(fn))

    def dispose(self):
        for dispose in self._effects:
            dispose()
        self._effects = []

    def applies(self):
        return True

    # contributions ----------------------------------------------------

    def tools(self):
        return []

    def bindings(self):
        return []

    def overlays(self):
        return []

    def wire(self, scene):
        """Register input handlers on a new scene (each draw creates one)."""


class Layer(Part):
    order = 50
    pick_kind = None

    def __init__(self):
        super().__init__()
        self._bound = None   # effects of bind() while it runs
        self._bound_for = None
        self._bound_effects = []
        self.renderers = computed(
            lambda: list(self.build()) if self.applies() else [], "renderers")

    def build(self):
        return []

    def bind(self, renderer):
        """Push values into a renderer with ``self.effect``."""

    def effect(self, fn):
        if self._bound is not None:
            self._bound.append(effect(fn))
        else:
            super().effect(fn)

    def pickables(self):
        """[(renderer, kind)] of the renderers that can be picked."""
        if self.pick_kind is None:
            return []
        return [(r, self.pick_kind) for r in self.renderers.value]

    def bind_all(self, renderers):
        """bind() the renderers of a draw; effects of replaced ones go."""
        if self._bound_for is not None and len(self._bound_for) == len(renderers) \
                and all(a is b for a, b in zip(self._bound_for, renderers)):
            return
        self._bound_for = list(renderers)
        for dispose in self._bound_effects:
            dispose()
        self._bound = []
        try:
            for r in renderers:
                self.bind(r)
        finally:
            bound, self._bound = self._bound, None
        self._bound_effects = bound

    def dispose(self):
        for dispose in self._bound_effects:
            dispose()
        self._bound_effects = []
        super().dispose()
