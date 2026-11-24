"""Field probe: click points, read values, plot the values along the line."""

import math

from ngapp.components import *

import cerbsim_ngapp_style as cb
from ..widgets import Segmented
from ..part import Part, Tool


class Probe(Part):
    """``evaluate(point)`` gives the value at a world point or None;
    ``on_plot(xs, ys)`` receives the values along the probe line."""

    key = "probe"

    def __init__(self, evaluate, on_plot=None):
        super().__init__()
        self.evaluate = evaluate
        self.on_plot = on_plot
        self.active = Observable(False, "probe_active")
        self.mode = Observable("points", "probe_mode")  # or "line"
        # (point, value or None, screen (x, y) of the click)
        self.points = Observable([], "probe_points")
        self.mode.on_change(lambda v, _o: self.clear())

    def tools(self):
        return [Tool(0, lambda: self.view.tool_button(
            "mdi-crosshairs-gps", "Line / point probe  →  plot", self.active.toggle,
            active=self.active), group=30)]

    def overlays(self):
        return [self._preview(), self._panel()]

    def wire(self, scene):
        scene.input_handler.on_click(self._on_click)

    def _panel(self):
        points, mode = self.points, self.mode

        def rows():
            line = mode.value == "line"
            out = []
            for i, (pt, val, _) in enumerate(points.value):
                label = "AB"[i] if line and i < 2 else f"P{i+1}"
                vtxt = "—" if val is None else f"{val:.4g}"
                out.append((i, f"{label}  ({pt[0]:.2f}, {pt[1]:.2f}, {pt[2]:.2f})", vtxt))
            return out

        def row(item):
            i, text, vtxt = item
            delx = Div(QIcon(ui_name="mdi-close"), ui_class=str(cb.probe_del))
            delx.on("click", lambda e=None: self.remove(i))
            return Div(Div(text, ui_class=str(cb.grow)), Div(vtxt, ui_class=str(cb.vp_probe_val)),
                       delx, ui_class=str(cb.vp_probe_pt))

        def hint():
            return Div(computed(
                lambda: "Click two points to define a cut line." if mode.value == "line"
                else "Click points on the field. Add 2 or more for a line plot."),
                ui_class=str(cb.vp_probe_hint))

        plot_btn = QBtn(
            ui_label="Plot line", ui_icon="mdi-chart-line", ui_color="primary",
            ui_dense=True, ui_no_caps=True, ui_size="sm", ui_class="full-width",
            ui_disable=computed(lambda: len(points.value) < 2))
        plot_btn.on_click(lambda e=None: self.plot())
        clear_btn = QBtn(ui_label="Clear", ui_flat=True, ui_dense=True,
                         ui_no_caps=True, ui_size="sm")
        clear_btn.on_click(lambda e=None: self.clear())
        return Div(
            Div(QIcon(ui_name="mdi-crosshairs-gps"), "Field probe", ui_class=str(cb.vp_probe_head)),
            Segmented([("points", "Points"), ("line", "Line")], mode),
            For(computed(rows), row, otherwise=hint),
            Div(plot_btn, clear_btn, ui_class="row items-center " + str(cb.gap_sm)),
            ui_class=str(cb.vp_probe),
            ui_hidden=computed(lambda: not self.active.value),
        )

    def _preview(self):
        """Screen-space marker dots + connecting segments for the points."""
        def marks():
            pts = [screen for _, _, screen in self.points.value]
            out = []
            for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                length = math.hypot(bx - ax, by - ay)
                angle = math.degrees(math.atan2(by - ay, bx - ax))
                out.append((str(cb.vp_preview_line), f"left:{ax}px;top:{ay}px;width:{length}px;"
                                                     f"transform:rotate({angle}deg);"))
            out += [(str(cb.vp_preview_dot), f"left:{x}px;top:{y}px;") for x, y in pts]
            return out

        return Div(For(computed(marks), lambda m: Div(ui_class=m[0], ui_style=m[1])),
                   ui_class=str(cb.vp_preview))

    def _on_click(self, event):
        if not self.active.value or event.get("button", 0) != 0:
            return
        p = self.view.scene.get_position(event["canvasX"], event["canvasY"])
        if p is None:
            return
        import numpy as np
        pt = np.array([float(p[0]), float(p[1]), float(p[2])])
        # CSS client coords (event x/y) for fixed-position overlay markers
        screen = (float(event.get("x", 0)), float(event.get("y", 0)))
        points = self.points.value
        # in line mode, a 3rd click starts a fresh segment
        if self.mode.value == "line" and len(points) >= 2:
            points = []
        self.points.value = [*points, (pt, self.evaluate(pt), screen)]

    def remove(self, i):
        points = self.points.value
        if 0 <= i < len(points):
            self.points.value = points[:i] + points[i + 1:]

    def clear(self):
        self.points.value = []

    def plot(self):
        if len(self.points.value) < 2 or self.on_plot is None:
            return
        import numpy as np
        pts = [p for p, _, _ in self.points.value]
        xs, ys = [], []
        total, per_seg = 0.0, 48
        for a, b in zip(pts[:-1], pts[1:]):
            seg = float(np.linalg.norm(b - a))
            for k in range(per_seg + 1):
                t = k / per_seg
                v = self.evaluate(a + (b - a) * t)
                xs.append(total + seg * t)
                ys.append(float("nan") if v is None else v)
            total += seg
        self.on_plot(xs, ys)
