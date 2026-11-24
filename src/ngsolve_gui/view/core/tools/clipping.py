"""Clipping plane: dock toggle, the bar along the top edge, Ctrl gestures on
the canvas and the ``c`` mode."""

import math

from ngapp.components import *

import cerbsim_ngapp_style as cb
from ..widgets import Segmented
from ..part import Binding, Part, Tool


class ClippingTools(Part):
    """Works on ``view.clipping`` (shared or not); ``global_toggle`` is an
    observable for the "clip all objects" button of the bar, if any."""

    key = "clipping"

    def __init__(self, global_toggle=None):
        super().__init__()
        self.enabled = self.observable("clipping_enabled", False)
        # offset in [-1, 1] of half the bounding box diagonal
        self.offset = Observable(0.0, "clip_offset", converter=float)
        self.axis = Observable("2", "clip_axis")
        self._global = global_toggle

    def attach(self, view):
        super().attach(view)
        view.top_bar_open = self.enabled
        self.axis.value = str(self.current_axis())
        self.enabled.on_change(lambda v, _o: self._push_enabled())
        self.offset.on_change(lambda v, _o: self._push_offset())

    @property
    def clipping(self):
        return self.view.clipping

    def _push_enabled(self):
        self.clipping.enable_clipping(self.enabled.value)
        self.view.render()

    def _push_offset(self):
        self.clipping.set_offset(self.offset.value * self.factor())
        self.view.render()

    # -- contributions ----------------------------------------------------

    def tools(self):
        return [Tool(0, lambda: self.view.tool_button(
            "mdi-content-cut", "Clipping plane  ·  c", self.enabled.toggle,
            active=self.enabled), group=20)]

    def overlays(self):
        return [self._bar()]

    def bindings(self):
        return [
            Binding("c", self.enabled.toggle, "Toggle clipping on/off", mode="c"),
            Binding("x", lambda: self.along_axis(0), "Clip along X axis", mode="c"),
            Binding("y", lambda: self.along_axis(1), "Clip along Y axis", mode="c"),
            Binding("z", lambda: self.along_axis(2), "Clip along Z axis", mode="c"),
            Binding("r", self.reset, "Reset clipping", mode="c"),
        ]

    def wire(self, scene):
        if self.clipping.mode == self.clipping.Mode.DISABLED:
            self.clipping.center = 0.5 * (scene.bounding_box[1] + scene.bounding_box[0])
        scene.input_handler.on_dblclick(self._on_dblclick, ctrl=True)
        scene.input_handler.on_drag(self._on_drag, ctrl=True)
        scene.input_handler.on_wheel(self._on_wheel, ctrl=True)

    def _bar(self):
        view = self.view
        axis_seg = Segmented([("0", "X"), ("1", "Y"), ("2", "Z")], self.axis,
                             lambda val: self.along_axis(int(val)))
        flip = view.tool_button("mdi-flip-horizontal", "Flip side",
                                lambda: self.along_axis(self.current_axis()), dock=False)
        slider = QSlider(
            ui_min=-1, ui_max=1, ui_step=0.01, ui_model_value=self.offset,
            ui_dense=True, ui_class=str(cb.vc_slider))
        value = Div(computed(lambda: f"{self.offset.value:.2f}"), ui_class=str(cb.vc_o_val))
        extra = []
        if self._global is not None:
            extra.append(view.tool_button("mdi-earth", "Clip all objects (global)",
                                          self._global.toggle, dock=False, active=self._global))
        close = view.tool_button("mdi-close", "Close clipping  ·  esc",
                                 lambda: setattr(self.enabled, "value", False), dock=False)
        return Div(
            Div(QIcon(ui_name="mdi-content-cut"), "Clip", ui_class=str(cb.vc_lab)),
            Div(axis_seg, ui_class=str(cb.vc_axis)),
            flip,
            Div(slider, value, ui_class=str(cb.vc_offset)),
            *extra,
            close,
            ui_class=str(cb.vp_clip),
            ui_hidden=computed(lambda: not self.enabled.value),
        )

    # -- actions ----------------------------------------------------------

    def current_axis(self):
        n = [abs(self.clipping.normal[i]) for i in range(3)]
        return n.index(max(n))

    def factor(self):
        try:
            bb = self.view.scene.bounding_box
        except Exception:
            bb = ((0, 0, 0), (1, 1, 1))
        d = [bb[1][i] - bb[0][i] for i in range(3)]
        return math.sqrt(sum(x * x for x in d)) / 2.0 or 1.0

    def set_offset(self, offset):
        """Offset in world units, clamped to the slider range."""
        self.offset.value = max(-1.0, min(1.0, offset / self.factor()))

    def along_axis(self, axis):
        """Clip along an axis; again along the same axis flips the side."""
        clip = self.clipping
        normal = [0.0, 0.0, 0.0]
        current = [clip.normal[i] for i in range(3)]
        if abs(current[axis]) > 0.9:
            normal[axis] = -1.0 if current[axis] > 0 else 1.0
        else:
            normal[axis] = 1.0
        clip.set_nx_value(normal[0])
        clip.set_ny_value(normal[1])
        clip.set_nz_value(normal[2])
        clip.set_offset(0)
        self.offset.value = 0.0
        self.axis.value = str(axis)
        if clip.mode == clip.Mode.DISABLED:
            self.enabled.value = True
        self.view.render()

    def reset(self):
        clip = self.clipping
        clip.set_nx_value(0.0)
        clip.set_ny_value(0.0)
        clip.set_nz_value(1.0)
        clip.set_offset(0)
        self.offset.value = 0.0
        bb = self.view.scene.bounding_box
        center = [0.5 * (bb[0][i] + bb[1][i]) for i in range(3)]
        clip.set_x_value(center[0])
        clip.set_y_value(center[1])
        clip.set_z_value(center[2])
        self.view.render()

    def apply_draw_option(self, clipping):
        """Draw(..., clipping=True | {"normal", "center", "offset"})."""
        clip = self.clipping
        if isinstance(clipping, dict):
            if "normal" in clipping:
                clip.normal = list(clipping["normal"])
            if "center" in clipping:
                clip.center = list(clipping["center"])
            if "offset" in clipping:
                clip.offset = clipping["offset"]
        if clipping:
            clip.mode = clip.Mode.PLANE
            self.enabled.value = True
            clip.enable_clipping(True)

    # -- gestures ---------------------------------------------------------

    def _on_dblclick(self, ev):
        p = self.view.scene.get_position(ev["canvasX"], ev["canvasY"])
        clip = self.clipping
        clip.set_x_value(float(p[0]))
        clip.set_y_value(float(p[1]))
        clip.set_z_value(float(p[2]))
        clip.set_offset(0)
        self.offset.value = 0.0
        self.view.render()

    def _on_drag(self, ev):
        clip = self.clipping
        if ev["buttons"] & 2:
            self.set_offset(clip.offset + ev["movementY"] * 0.0002 * self.factor())
            self.view.render()
        if ev["buttons"] & 1:
            import numpy.linalg

            transform = self.view.scene.options.camera.transform.copy()
            inv_normal_mat = transform._mat.copy()[:3, :3].T
            normal_mat = numpy.linalg.inv(inv_normal_mat)
            transform._mat = numpy.identity(4)
            transform._mat[:3, :3] = normal_mat
            s = 0.3
            transform.rotate(s * ev["movementY"], s * ev["movementX"])
            n = inv_normal_mat @ (transform._mat[:3, :3] @ clip.normal)
            clip.set_nx_value(float(n[0]))
            clip.set_ny_value(float(n[1]))
            clip.set_nz_value(float(n[2]))
            self.view.render()

    def _on_wheel(self, ev):
        self.set_offset(self.clipping.offset + ev["deltaY"] * 0.0005 * self.factor())
        self.view.render()
