"""Viewport: the canvas, the scene assembled from the renderers of its
layers, the tool dock and overlays of its parts, theme and camera handling."""

import threading
from contextlib import contextmanager

from ngapp.components import *
from ngapp.observable import add_flush_hook, current_batch
from webgpu import Background
from webgpu.camera import Camera
from webgpu.clipping import Clipping
from webgpu.labels import Labels
from webgpu.webgpu_api import Color

from ... import cerbsim_style as cb
from .defaults import Defaults
from .keymap import merge
from .part import Layer, has_role

_dirty = set()
_dirty_lock = threading.Lock()


def _render_dirty():
    with _dirty_lock:
        views = list(_dirty)
        _dirty.clear()
    for view in views:
        view.render_now()


# one render per event and viewport, after the effects pushed their values
add_flush_hook(_render_dirty, "effect")


def sync_default_viewport_clear():
    """Set the webgpu Canvas default clear color from the active theme so a new
    scene renders the right background on its very first frame (no flash)."""
    from webgpu.canvas import set_default_clear_color
    key = "dark" if cb._active_theme == "dark" else "light"
    set_default_clear_color(Color(*cb.VIEWPORT_CLEAR[key], 1))


def _theme_scene(scene, bg_rgb, text_rgb):
    """Recursively theme a scene's overlays: Background backdrops match the
    viewport clear color; default-colored Labels (mesh stats, colorbar ticks)
    use the in-viewport text color. Per-label colored Labels are left alone."""
    def _walk(ro):
        if isinstance(ro, Background):
            ro.bg_color = bg_rgb
        elif isinstance(ro, Labels) and ro.colors is None:
            ro.text_color = text_rgb
        for sub in getattr(ro, "render_objects", []):
            _walk(sub)

    for ro in getattr(scene, "render_objects", []):
        _walk(ro)


class Viewport(Div):
    """A view assembled from parts.

    The scene is drawn again whenever the renderers of a layer change; each
    draw creates a new webgpu scene, whose input handlers the parts register
    again in ``wire``. ``camera`` and ``clipping`` may be shared with other
    viewports.
    """

    def __init__(self, *, camera=None, clipping=None, defaults=None, state=None, **kwargs):
        self.wgpu = WebgpuComponent()
        self.wgpu.ui_class = "fit"
        self.camera = camera or Camera()
        self._clipping = Observable(clipping or Clipping(), "clipping")
        self.defaults = defaults or Defaults()
        # a bar along the top edge is open (tooltips of the dock move below it)
        self.top_bar_open = Observable(False, "top_bar_open")
        self._saved = dict(state or {})
        self._parts = {}
        self._layers = Observable((), "layers")
        self._overlays = []
        self._dock = Div(ui_class=cb.vp_dock)
        self.scene_objects = computed(self._scene_objects, "scene_objects")
        self.scene_objects.on_change(lambda _new, _old: self.draw())
        self._last_view = (None, False)
        self._hold = 0
        self._drawn = None
        self.draws = 0
        super().__init__(self.wgpu, self._dock, ui_class="relative-position fit", **kwargs)
        self.on_mounted(self.apply_theme)
        # the canvas is created in the component's own "mounted" handler; ours
        # runs after it, so the canvas is ready when we set the clear color
        self.wgpu.on("mounted", lambda *a: self.apply_theme())

    @property
    def scene(self):
        return self.wgpu.scene

    @property
    def renderers(self):
        """The renderers drawn last."""
        return list(self._drawn or ())

    def with_role(self, role):
        return [r for r in self._drawn or () if has_role(r, role)]

    @property
    def clipping(self):
        """The clipping plane; renderers are built again when it is swapped."""
        return self._clipping.value

    @clipping.setter
    def clipping(self, value):
        self._clipping.value = value

    # -- parts ------------------------------------------------------------

    def add(self, *parts):
        for part in parts:
            if part.key in self._parts:
                raise ValueError(f"part {part.key!r} added twice")
            self._parts[part.key] = part
            part.attach(self)
            part.load_state(self._saved)
            self._overlays += part.overlays()
        self._layers.value = tuple(
            sorted((p for p in self._parts.values() if isinstance(p, Layer)),
                   key=lambda layer: layer.order))
        tools = sorted((t for p in self._parts.values() for t in p.tools()),
                       key=lambda t: (t.group, t.order))
        dock = []
        for i, tool in enumerate(tools):
            if i and tool.group != tools[i - 1].group:
                dock.append(Div(ui_class=str(cb.vp_sep)))
            dock.append(tool.build())
        self._dock.ui_children = dock
        self.ui_children = [self.wgpu, self._dock, *self._overlays]

    def add_overlay(self, component):
        self._overlays.append(component)
        self.ui_children = [self.wgpu, self._dock, *self._overlays]

    @contextmanager
    def hold(self):
        """No draws while assembling: the first draw comes from outside."""
        self._hold += 1
        try:
            yield
        finally:
            self._hold -= 1

    def part(self, key):
        return self._parts.get(key)

    @property
    def parts(self):
        return list(self._parts.values())

    def state(self):
        out = {}
        for part in self._parts.values():
            out.update(part.state())
        return out

    def load_state(self, values):
        for part in self._parts.values():
            part.load_state(values)

    def keymap(self, extra=None):
        bindings = [b for p in self._parts.values() if p.applies() for b in p.bindings()]
        return merge(bindings, extra)

    # -- scene ------------------------------------------------------------

    def _scene_objects(self):
        return [r for layer in self._layers.value for r in layer.renderers.value]

    def draw(self):
        """Draw the renderers of the layers, unless they are drawn already."""
        objects = self.scene_objects.value
        if not objects or self._hold:
            return None
        if self.scene is not None and self._drawn is not None and len(self._drawn) == len(objects) \
                and all(a is b for a, b in zip(self._drawn, objects)):
            return self.scene
        self._drawn = list(objects)
        self.draws += 1
        for layer in self._layers.value:
            layer.bind_all(layer.renderers.value)
        for part in list(self._parts.values()):
            part.prepare(objects)
        scene = self.wgpu.draw(objects, camera=self.camera)
        for part in list(self._parts.values()):
            part.wire(scene)
        return scene

    def dispose(self):
        for part in self._parts.values():
            part.dispose()

    def render(self):
        """Render once at the end of the running event (now outside events)."""
        if current_batch() is None:
            self.render_now()
            return
        with _dirty_lock:
            _dirty.add(self)

    def render_now(self):
        if self.scene is not None:
            self.scene.render()

    def redraw(self):
        if self.scene is not None:
            self.scene.redraw()

    def apply_theme(self):
        """Set the scene background (clear color + overlays) from the active theme.

        Reads the ``data-theme`` attribute, which ``install``/``set_theme`` set
        from the stored preference (resolving "system" via the OS), available by
        the time the canvas mounts.
        """
        def _apply(js):
            scene = self.scene
            canvas = getattr(scene, "canvas", None) if scene is not None else None
            if canvas is None:
                return
            key = "dark" if cb.is_dark(js) else "light"
            canvas.clear_color = Color(*cb.VIEWPORT_CLEAR[key], 1)
            _theme_scene(scene, cb.VIEWPORT_CLEAR[key], cb.VIEWPORT_TEXT[key])
            scene.render()

        self.call_js(_apply)

    # -- camera -----------------------------------------------------------

    def fit(self):
        if self.scene is not None:
            pmin, pmax = self.scene.bounding_box
            self.scene.options.camera.reset(pmin, pmax)
            self.render()

    def set_view(self, plane):
        """Look onto a plane (``"xy"``, ``"xz"``, ``"yz"``); repeating the same
        view looks from the opposite side."""
        last, flip = self._last_view
        flip = not flip if last == plane else False
        getattr(self.scene.options.camera, f"reset_{plane}")(flip=flip)
        self._last_view = (plane, flip)
        self.render()

    def set_orthographic(self, value):
        camera = self.scene.options.camera
        if camera.orthographic != value:
            camera.set_orthographic(value)
            self.render()

    def set_camera(self, camera):
        """Drive the view by another camera (moving observers and input wiring)."""
        self.camera = camera
        scene = self.scene
        if scene is None or scene.options.camera is camera:
            return
        old = scene.options.camera
        old.unregister_callbacks(scene.input_handler)
        old.unregister_observer(scene._on_camera_changed)
        scene.options.camera = camera
        camera.register_observer(scene._on_camera_changed)
        scene._wire_input(camera)
        self.sync_camera()

    def sync_camera(self):
        """Push the camera state into the live scene.

        While a scene is visible the JS engine owns the camera, so moves made
        in one view only reach other views sharing that camera when they are
        shown again.
        """
        scene = self.scene
        if scene is None or scene.canvas is None:
            return
        camera = self.camera
        if scene.options.camera is not camera:
            self.set_camera(camera)
            return
        if scene._render_mutex is not None:
            with scene._render_mutex:
                scene._select_buffer_valid = False
        engine = getattr(scene, "_js_engine", None)
        if engine is None:
            scene.options.update_buffers()
            return
        camera.register_observer(scene._on_camera_changed)
        scene._wire_input(camera)
        import webgpu.platform as platform

        t = camera.transform
        center = t._center.tolist() if hasattr(t._center, "tolist") else list(t._center)
        try:
            engine.setCameraTransform(
                platform.toJS(t._mat.flatten().tolist()), platform.toJS(list(center))
            )
            engine.setProjection(camera.orthographic)
        except Exception as e:
            print(f"warning: camera sync failed: {e}")

    # -- dock helpers -----------------------------------------------------

    def dock_tip(self, text):
        """Tooltip of a dock button, moved below an open top bar."""
        return QTooltip(text, ui_anchor="bottom middle", ui_self="top middle",
                        ui_offset=computed(lambda: [0, 58 if self.top_bar_open.value else 10]),
                        ui_delay=300)

    def tool_button(self, icon, tip, handler, active=None, dock=True):
        """A dock button, highlighted while ``active``."""
        from ...prop_widgets import on_cls

        tooltip = self.dock_tip(tip) if dock else QTooltip(tip)
        cls = on_cls(cb.vp_tool, cb.vp_tool_on, active) if active is not None else str(cb.vp_tool)
        btn = Div(QIcon(ui_name=icon), tooltip, ui_class=cls)
        btn.on("click", lambda e=None: handler())
        return btn
