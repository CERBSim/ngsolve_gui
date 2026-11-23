"""ViewTab: a viewport in a tab of the GUI, bound to AppData (shared cameras,
global clipping, GPU cache) and the user settings."""

from ngapp.components import *
from ngapp.observable import snapshot
from webgpu.camera import Camera
from webgpu.clipping import Clipping

from .property_panel import PropertyPanelMixin
from .settings import usersettings
from .undo import UndoStack
from .view.core import Binding, Part, Picking, Raw, SettingsDefaults, Tool, Viewport
from .view.core.tools.bookmarks import Bookmarks
from .view.core.tools.camera import CameraTools, Gizmos
from .view.core.tools.clipping import ClippingTools
from .view.core.tools.fullscreen import Fullscreen
from .view.core.tools.probe import Probe
from . import cerbsim_style as cb


class _TabTools(Part):
    """Dock tools and bindings that belong to the tab, not the view."""

    key = "tab"

    def __init__(self, tab):
        super().__init__()
        self.tab = tab

    def tools(self):
        tab, view = self.tab, self.view
        tools = []
        if tab._camera_linkable():
            tools.append(Tool(5, tab._link_button))
        if hasattr(tab, "wireframe_visible") and view.part("wireframe") is None:
            tools.append(Tool(20, lambda: view.tool_button(
                "mdi-grid", "Wireframe  ·  w", tab.wireframe_visible.toggle,
                active=tab.wireframe_visible)))
        return tools

    def bindings(self):
        return [
            Binding("u", self.tab.undo_last, "Undo last action"),
            Binding("l", self.tab.toggle_camera_link, "Share/detach camera", mode="v"),
        ]


class ViewTab(PropertyPanelMixin, Div):
    """Subclasses set their data attributes (``mesh``, ``cf``, ``geo``) before
    calling ``__init__``. They either add layers in ``view_parts()`` or
    implement ``draw()``, which passes the renderers to ``show()``. Key
    bindings beyond the view's come from ``tab_keybindings()``."""

    _picking_always_active = False

    def __init__(self, name, data, app_data):
        self.name = name
        self.data = data
        self.app_data = app_data
        self.icon = "mdi-vector-triangle"
        self.undo_stack = UndoStack()
        self._last_pick = None
        self._pick_mesh = None

        data_dict = data if isinstance(data, dict) else {}
        saved = app_data.saved_settings()
        self.camera_shared = Observable(
            saved.get("camera_shared", not data_dict.get("detached_camera", False)),
            "camera_shared")
        given = data_dict.get("camera")
        if isinstance(given, Camera):
            import numpy as np

            self._camera_group = None
            self._shared_camera = given
            fresh = bool(np.allclose(given.transform.mat, np.identity(4)))
        else:
            self._camera_group = self._resolve_camera_group()
            self._shared_camera, fresh = app_data.get_shared_camera(self._camera_group)
        self._own_camera = None if self.camera_shared.value else Camera()
        camera_needs_fit = fresh or not self.camera_shared.value

        self.use_global_clipping = Observable(
            saved.get("use_global_clipping", data_dict.get("global_clipping", True)),
            "use_global_clipping")
        # used instead of the shared plane while use_global_clipping is off
        self._local_clipping = Clipping()

        view = self.view = Viewport(
            camera=self.camera, clipping=self.clipping,
            defaults=SettingsDefaults(usersettings), state=saved)
        self.picking = Picking(
            self._pick_result, lambda r: self._pick_info(r),
            always=self._picking_always_active,
            on_select=lambda ev, kind: self._on_pick_select(ev, kind),
            on_out=lambda ev: self._on_pick_out(ev),
            on_background=lambda ev: self._on_pick_background(ev))
        self._raw = Raw("scene")
        self.gizmos = Gizmos()
        with view.hold():
            view.add(*self.view_parts())
            view.add(self._raw, self.gizmos, CameraTools(axes=self._supports_clipping()),
                     _TabTools(self))
            if self._supports_clipping():
                view.add(ClippingTools(self.use_global_clipping))
            view.add(self.picking)
            legend = self._build_viewport_legend()
            if legend is not None:
                view.add_overlay(legend)
            if self._supports_probe():
                view.add(Probe(self._probe_value, self._plot_probe))
            view.add(Fullscreen(), Bookmarks())
        super().__init__(view, ui_class="relative-position fit")

        self.draw()
        if camera_needs_fit:
            self.reset_camera()
        clip = view.part("clipping")
        if "clipping" in data_dict and clip is not None:
            clip.apply_draw_option(data_dict["clipping"])

        self.camera_shared.on_change(self._apply_camera_shared)
        self.use_global_clipping.on_change(self._apply_global_clipping)

    # -- view --------------------------------------------------------------

    def show(self, renderers, pickables=(), pick_mesh=None):
        """Draw the renderers (gizmos are added by the view); returns the scene."""
        self._pick_mesh = pick_mesh
        draws = self.view.draws
        self._raw.set(renderers, pickables)
        if self.view.draws == draws:
            self.view.draw()
        return self.scene

    def view_parts(self):
        """Parts added to the view before the generic ones."""
        return []

    def draw(self):
        self.view.draw()

    @property
    def wgpu(self):
        return self.view.wgpu

    @property
    def scene(self):
        return self.view.wgpu.scene

    @property
    def pick_overlay(self):
        return self.picking.overlay

    @property
    def picking_enabled(self):
        return self.picking.enabled

    @property
    def coordinate_axes(self):
        return self.gizmos.axes

    @property
    def navigation_cube(self):
        return self.gizmos.navcube

    @property
    def axes_visible(self):
        return self.gizmos.axes_visible

    @property
    def navcube_visible(self):
        return self.gizmos.navcube_visible

    @property
    def clipping_enabled(self):
        return self.view.part("clipping").enabled

    def redraw(self):
        self.view.redraw()

    def apply_viewport_theme(self):
        self.view.apply_theme()

    def reset_camera(self):
        self.view.fit()

    def set_view(self, plane):
        self.view.set_view(plane)

    def set_orthographic(self, value):
        self.view.set_orthographic(value)

    def toggle_clipping(self):
        self.clipping_enabled.toggle()

    def clip_along_axis(self, axis):
        self.view.part("clipping").along_axis(axis)

    def reset_clipping(self):
        self.view.part("clipping").reset()

    def undo_last(self):
        """Revert the most recent undoable action (region hides etc.)."""
        label = self.undo_stack.undo()
        if label:
            self.pick_overlay.show_info("Undone", [("action", label)])

    def saved_state(self):
        """Saved settings: the tab's observables and the view's state."""
        return {**snapshot(self), **self.view.state()}

    def dispose(self):
        self.view.dispose()

    @property
    def title(self):
        rec = self.app_data.get_tab(self.name)
        return rec["title"] if rec is not None else self.name

    def _supports_clipping(self):
        return not hasattr(self, "mesh") or self.mesh.dim == 3

    def _supports_probe(self):
        return hasattr(self, "cf")

    def _build_viewport_legend(self):
        """Override to return an in-viewport colorbar legend (fields only)."""
        return None

    # -- key bindings -------------------------------------------------------

    def get_keybindings(self):
        return self.view.keymap(self.tab_keybindings())

    def tab_keybindings(self):
        """Bindings of the tab in the format of ngapp.keybindings; modes with
        a trigger the view uses too are merged."""
        return {"flat": [], "modes": []}

    # -- camera --------------------------------------------------------------

    @property
    def camera(self):
        """The camera driving this view: the mesh/geometry-wide one, or (when
        detached) this view's own."""
        if self.camera_shared.value:
            return self._shared_camera
        if self._own_camera is None:
            self._own_camera = Camera()
        return self._own_camera

    def _resolve_camera_group(self):
        """The object all views sharing this camera have in common: the geometry
        a mesh was generated from, else the mesh itself (``None`` = no sharing).
        """
        geo = getattr(self, "geo", None)
        if geo is not None:
            return geo
        mesh = getattr(self, "mesh", None)
        if mesh is None:
            return None
        try:
            from netgen.meshing import NetgenGeometry

            geo = mesh.ngmesh.GetGeometry()
            # Meshes without a geometry all report the same dummy base object.
            if geo is not None and type(geo) is not NetgenGeometry:
                return geo
        except Exception:
            pass
        return mesh

    def _camera_linkable(self):
        # a camera handed over by the caller (a view replacing another one) is
        # shared as well; keeping the tool also keeps the dock layout stable
        given = self.data.get("camera") if isinstance(self.data, dict) else None
        return self._camera_group is not None or isinstance(given, Camera)

    def _link_button(self):
        shared = self.camera_shared
        icon = QIcon(ui_name=computed(
            lambda: "mdi-link-variant" if shared.value else "mdi-link-variant-off"))
        tip = self.view.dock_tip(computed(
            lambda: "Camera shared with other views of this mesh  ·  click to detach"
            if shared.value else "Camera detached  ·  click to share again"))
        from .prop_widgets import on_cls
        btn = Div(icon, tip, ui_class=on_cls(cb.vp_tool, cb.vp_tool_on, shared))
        btn.on("click", lambda e=None: self.toggle_camera_link())
        return btn

    def toggle_camera_link(self):
        """Link this view's camera to the other views on this mesh, or detach it."""
        self.camera_shared.toggle()

    def _apply_camera_shared(self, val, _old):
        if not val:
            # detach from the current view, not from wherever the own camera was
            cam = Camera()
            cam.transform = self._shared_camera.transform.copy()
            cam.orthographic = self._shared_camera.orthographic
            self._own_camera = cam
        self.view.set_camera(self.camera)

    def sync_camera(self):
        self.view.camera = self.camera
        self.view.sync_camera()

    # -- clipping ------------------------------------------------------------

    @property
    def clipping(self):
        if not self.use_global_clipping.value:
            return self._local_clipping
        return self.app_data.clipping

    def _apply_global_clipping(self, val, _old):
        self.view.clipping = self.clipping
        clip = self.view.part("clipping")
        self.clipping.enable_clipping(clip is not None and clip.enabled.value)
        # renderers keep the clipping object they were built with
        self.draw()

    # -- picking -------------------------------------------------------------

    def _pick_result(self, event, kind):
        from ngsolve_webgpu.pick import MeshPickResult

        return MeshPickResult(event, self._pick_mesh, self.scene.options, kind=kind)

    def _on_pick_select(self, event, kind="surface"):
        self.picking.select(event, kind)
        self._last_pick = self.picking.last

    def _on_pick_out(self, ev):
        self._last_pick = None
        self.picking.out(ev)

    def _on_pick_background(self, ev):
        self._last_pick = None
        self.picking.background(ev)

    @property
    def _highlights(self):
        return self.picking.highlights

    def _clear_highlight(self):
        self.picking.clear_highlight()

    def _kind_label(self, result):
        """Element kind label. The 'surface' renderer draws codim-0 (VOL)
        elements on a 2D mesh, but boundary (BND) elements on a 3D mesh."""
        dim = getattr(getattr(self, "mesh", None), "dim", 3)
        if result.kind == "surface":
            return "vol el." if dim == 2 else "surf el."
        if result.kind == "volume":
            return "vol el."
        if result.kind == "clipping":
            return "clip"
        return f"{result.kind} el."

    def _pick_info(self, result):
        """Structured pick info: (header, [(label, value), ...], accent_last)."""
        pos = result.world_pos
        rows = [
            ("kind", self._kind_label(result)),
            ("element", f"#{result.element_nr}"),
            ("region", result.region_name or "—"),
            ("xyz", f"{pos[0]:.5f}, {pos[1]:.5f}, {pos[2]:.5f}"),
        ]
        return ("Picked element", rows, False)

    # -- probe ---------------------------------------------------------------

    def _probe_mesh_point(self, Q):
        """Map a picked world point back to the *undeformed* mesh point.

        With deformation on, picking returns the deformed surface position; the
        coefficient function lives on the undeformed mesh. Recover the original
        point P with Q = P + scale·deform(P) via fixed-point iteration.
        """
        import numpy as np
        Q = np.array([float(Q[0]), float(Q[1]), float(Q[2])], dtype=float)
        deform = getattr(self, "deformation", None)
        enabled = getattr(self, "deformation_enabled", None)
        if deform is None or enabled is None or not enabled.value:
            return Q
        try:
            scale = float(self.deformation_scale.value) * float(self.deformation_scale2.value)
        except Exception:
            return Q
        if scale == 0.0:
            return Q
        P = Q.copy()
        for _ in range(12):
            try:
                mip = self.mesh(*[float(P[i]) for i in range(self.mesh.dim)])
                d = np.asarray(deform(mip), dtype=float).ravel()
            except Exception:
                return Q
            dv = np.zeros(3)
            dv[:min(3, d.size)] = d[:3]
            newP = Q - scale * dv
            if np.linalg.norm(newP - P) < 1e-10:
                P = newP
                break
            P = newP
        return P

    def _probe_value(self, pt):
        """The field at a picked world point (norm for vectors), mapped back
        through any active deformation. None if outside the mesh."""
        try:
            import numpy as np
            P = self._probe_mesh_point(pt)
            mip = self.mesh(*[float(P[i]) for i in range(self.mesh.dim)])
            v = self.cf(mip)
            if isinstance(v, (tuple, list, np.ndarray)):
                return float(np.linalg.norm(np.real(np.asarray(v, dtype=complex))))
            return float(np.real(v))
        except Exception:
            return None

    def _plot_probe(self, xs, ys):
        try:
            import plotly.graph_objects as go
        except Exception:
            return
        fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#2f6fe5", width=2)))
        fig.update_layout(
            title=f"Line probe — {self.title}",
            xaxis_title="arc length", yaxis_title="value",
            template="plotly_white", margin=dict(l=55, r=20, t=44, b=44),
        )
        from .plot import PlotComponent
        self.app_data.add_tab(
            f"{self.title} — line probe", PlotComponent, {"obj": fig}, self.app_data)
