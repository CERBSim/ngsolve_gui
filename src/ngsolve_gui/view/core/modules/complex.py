"""Display of complex fields: real/imag/abs/arg and the phase animation."""

from ngapp.components import Observable, untracked

from ..part import Binding, Part, has_role


class Complex(Part):
    """Works on the drawn renderers with the role ``"complex"``."""

    key = "complex"
    requires = ("field",)

    def __init__(self):
        super().__init__()
        self.mode = self.observable("complex_mode", "real")
        self.speed = self.observable("complex_speed", 1.0, converter=float)
        self.animate = Observable(False, "complex_animate")
        self._animated = []

    def attach(self, view):
        super().attach(view)
        self.field = view.part("field")
        self.effect(self._push_mode)
        self.effect(self._push_animate)
        self.effect(self._push_speed)

    def applies(self):
        return self.field.is_complex

    def _stop(self):
        for r in self._animated:
            r.stop_animation()
        self._animated = []

    def _start(self, scene):
        self._stop()
        if scene is None:
            return
        self._animated = self.view.with_role("complex")
        speed = untracked(lambda: self.speed.value)
        for r in self._animated:
            r.animate_phase(scene, speed=speed)

    def prepare(self, renderers):
        mode = self.mode.value
        for r in renderers:
            if has_role(r, "complex"):
                r.set_complex_mode(mode)

    def wire(self, scene):
        if self.animate.value:
            self._start(scene)

    def _push_mode(self):
        mode = self.mode.value
        if self.animate.value:
            return
        for r in self.view.with_role("complex"):
            r.set_complex_mode(mode)
        self.view.render()

    def _push_animate(self):
        if self.animate.value:
            colormap = self.view.part("colormap")
            if colormap is not None:
                colormap.autoscale.value = False
            self._start(self.view.scene)
        else:
            self._stop()
            mode = self.mode.value
            for r in self.view.with_role("complex"):
                r.set_complex_mode(mode)
            self.view.render()

    def _push_speed(self):
        speed = self.speed.value
        for r in self._animated:
            if r._phase_animation is not None:
                r._phase_animation.speed = speed

    def _set(self, mode):
        self.mode.value = mode

    def bindings(self):
        return [
            Binding("r", lambda: self._set("real"), "Real part", mode="x"),
            Binding("i", lambda: self._set("imag"), "Imag part", mode="x"),
            Binding("a", lambda: self._set("abs"), "Absolute value", mode="x"),
            Binding("p", lambda: self._set("arg"), "Phase/Arg", mode="x"),
            Binding("space", self.animate.toggle, "Toggle animation", mode="x"),
        ]
