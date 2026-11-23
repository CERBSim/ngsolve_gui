"""Camera tools (fit, look along an axis, projection) and gizmos."""

from ngapp.components import Div, Observable
from webgpu import CoordinateAxes, NavigationCube

from .... import cerbsim_style as cb
from ..part import Binding, Layer, Part, Tool


class CameraTools(Part):
    key = "camera"

    def __init__(self, axes=True):
        super().__init__()
        self._axes = axes

    def tools(self):
        view = self.view
        tools = [Tool(0, lambda: view.tool_button("mdi-overscan", "Fit view  ·  r", view.fit))]
        if self._axes:
            for i, (axis, plane) in enumerate((("x", "yz"), ("y", "xz"), ("z", "xy"))):
                tools.append(Tool(10 + i, lambda axis=axis, plane=plane: self._axis_button(axis, plane)))
        return tools

    def _axis_button(self, axis, plane):
        btn = Div(Div(axis.upper(), ui_style="font-weight: 600; font-size: 12px;"),
                  self.view.dock_tip(f"Look along {axis.upper()}  ·  v {axis}  (again: opposite side)"),
                  ui_class=str(cb.vp_tool))
        btn.on("click", lambda e=None: self.view.set_view(plane))
        return btn

    def bindings(self):
        view = self.view
        return [
            Binding("r", view.fit, "Reset camera"),
            Binding("x", lambda: view.set_view("yz"), "Look along X", mode="v"),
            Binding("y", lambda: view.set_view("xz"), "Look along Y", mode="v"),
            Binding("z", lambda: view.set_view("xy"), "Look along Z", mode="v"),
            Binding("o", lambda: view.set_orthographic(True), "Orthographic", mode="v"),
            Binding("p", lambda: view.set_orthographic(False), "Perspective", mode="v"),
            Binding("r", view.fit, "Reset", mode="v"),
        ]


class Gizmos(Layer):
    """Coordinate axes and navigation cube; their visibility follows the
    defaults, the keys toggle it per view."""

    key = "gizmos"
    order = 90

    def __init__(self):
        super().__init__()
        self.axes = CoordinateAxes()
        self.navcube = NavigationCube()
        self.navcube.faces.on_select(self._on_face)
        self.axes_visible = Observable(True, "axes_visible")
        self.navcube_visible = Observable(False, "navcube_visible")

    def attach(self, view):
        super().attach(view)
        axes = view.defaults.ref("axes_visible", True, bool)
        navcube = view.defaults.ref("navcube_visible", False, bool)
        for own, default in ((self.axes_visible, axes), (self.navcube_visible, navcube)):
            own.value = default.value
            # a change of the default reaches open views
            view.effect(lambda own=own, default=default: setattr(own, "value", default.value))
        self.effect(self._push)

    def _push(self):
        self.axes.active = self.axes_visible.value
        self.navcube.active = self.navcube_visible.value
        self.view.render()

    def build(self):
        return [self.axes, self.navcube]

    def bindings(self):
        return [
            Binding("a", self.axes_visible.toggle, "Toggle axes", mode="s"),
            Binding("n", self.navcube_visible.toggle, "Toggle nav cube", mode="s"),
        ]

    def wire(self, scene):
        def select(event):
            # right click selects (the nav cube faces)
            if event["button"] == 2:
                try:
                    scene.select(event["canvasX"], event["canvasY"])
                except AttributeError:
                    pass
        scene.input_handler.on_click(select)

    def _on_face(self, event):
        face_id = event.uint32[1]
        views = NavigationCube.FACE_VIEWS
        if face_id >= len(views):
            return
        view = views[face_id]
        camera = self.view.scene.options.camera
        if view.endswith("_flip"):
            getattr(camera, f"reset_{view[:-5]}")(flip=True)
        else:
            getattr(camera, f"reset_{view}")()
        self.view.render()
