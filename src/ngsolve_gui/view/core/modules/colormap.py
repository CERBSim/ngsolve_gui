"""Colormap of the field layers: name, range, autoscale (over the visible
regions), discrete steps; the ``m`` mode."""

from ngapp.components import untracked
from webgpu.colormap import Colormap as _Colormap

from .... import cerbsim_style as cb
from ..part import Binding, Part

NAMES = ["rainbow", "turbo", "viridis", "plasma", "cet_l20", "matlab:jet", "matplotlib:coolwarm"]


class Colormap(Part):
    """One webgpu Colormap per view, kept over rebuilds; layers pass
    ``colormap.colormap`` to their renderers."""

    key = "colormap"
    requires = ("field",)

    def __init__(self):
        super().__init__()
        self.name = self.observable("colormap_name", "rainbow")
        self.autoscale = self.observable("colormap_autoscale", True)
        self.discrete = self.observable("colormap_discrete", False)
        fmt = lambda v: f"{v:.4g}"
        self.min = self.observable("colormap_min", 0.0, converter=float, formatter=fmt)
        self.max = self.observable("colormap_max", 1.0, converter=float, formatter=fmt)
        self.ncolors = self.observable("ncolors_colormap", 8, converter=int)
        self.colormap = None
        self._full_range = None

    def attach(self, view):
        super().attach(view)
        defaults = view.defaults
        self.name.value = cb.default_colormap(defaults)
        self.discrete.value = bool(defaults.get("default_discrete_colormap", False))
        self.ncolors.value = int(defaults.get("default_ncolors", 8))
        self.field = view.part("field")
        self.colormap = _Colormap(colormap=self.name.value)
        self.colormap._callbacks.append(self._sync_range)
        view.wgpu.on_mounted(self._sync_range)
        for fn in (self._push_name, self._push_discrete, self._push_ncolors,
                   self._push_autoscale, self._push_range, self._push_visible_range):
            self.effect(fn)

    def _sync_range(self):
        """The renderers widen the range while autoscaling."""
        if untracked(lambda: self.autoscale.value):
            self.min.value = float(self.colormap.minval)
            self.max.value = float(self.colormap.maxval)

    def _push_name(self):
        self.colormap.set_colormap(self.name.value)
        self.view.render()

    def _push_discrete(self):
        self.colormap.set_discrete(self.discrete.value)
        self.view.render()

    def _push_ncolors(self):
        self.colormap.set_n_colors(max(1, min(32, self.ncolors.value)))
        self.view.render()

    def _push_autoscale(self):
        self.colormap.autoscale = self.autoscale.value
        if self.autoscale.value:
            self._redraw_and_sync()

    def _push_range(self):
        # while autoscaling, the colormap writes the range, not the other way
        lo, hi = self.min.value, self.max.value
        if self.autoscale.value:
            return
        self.colormap.set_min(lo)
        self.colormap.set_max(hi)
        self.view.render()

    def _redraw_and_sync(self):
        scene = self.view.scene
        if scene is not None and getattr(scene, "canvas", None) is not None:
            scene.redraw(blocking=True)
            self._sync_range()

    # -- autoscale over the visible regions -------------------------------

    def _push_visible_range(self):
        regions = self.view.part("regions")
        data = self.field.data.value
        if regions is None or data is None:
            return
        st = regions.sync()
        surface = self._visible_layer("surface")
        clipfield = self._visible_layer("clipfield")
        with untracked():
            if self._full_range is None and data._timestamp >= 0:
                self._full_range = (list(data.minval), list(data.maxval))
            if not st.any_hidden():
                if self._full_range is not None:
                    data.minval, data.maxval = (list(self._full_range[0]),
                                                list(self._full_range[1]))
            else:
                mm = self._visible_range(data, st, surface, clipfield)
                if mm is not None:
                    data.minval, data.maxval = mm
            if self.autoscale.value:
                self._redraw_and_sync()

    def _visible_layer(self, key):
        layer = self.view.part(key)
        return layer is not None and bool(layer.renderers.value) and layer.visible.value

    def _visible_range(self, data, st, surface, clipfield):
        mats = [m for m in st.unique_materials if m not in st.hidden]
        if not mats:
            return None
        if data.mesh_data.dim != 3:
            return data.compute_range(materials=mats)
        boundaries = st.visible_boundary_names() if surface else None
        use_mats = clipfield or not boundaries
        return data.compute_range(materials=mats if use_mats else None, boundaries=boundaries)

    # -- bindings ---------------------------------------------------------

    def cycle(self, direction):
        try:
            idx = NAMES.index(self.name.value)
        except ValueError:
            idx = 0
        self.name.value = NAMES[(idx + direction) % len(NAMES)]

    def bindings(self):
        return [
            Binding("a", self.autoscale.toggle, "Toggle autoscale", mode="m"),
            Binding("d", self.discrete.toggle, "Toggle discrete", mode="m"),
            Binding("n", lambda: self.cycle(1), "Next colormap", mode="m"),
            Binding("p", lambda: self.cycle(-1), "Previous colormap", mode="m"),
        ]
