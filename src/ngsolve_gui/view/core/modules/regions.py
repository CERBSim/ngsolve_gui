"""Region visibility: hidden volume regions and boundary overrides, drawn
through one alpha buffer that the viewport hands to its renderers."""

from ngapp.components import Observable, batch
from ngsolve_webgpu.region_visibility import RegionState, RegionVisibility

from ..part import Binding, Part


class Regions(Part):
    """``undo(label, restore)`` records changes, if given; ``on_change`` are
    called after the alphas changed (autoscale, LIC)."""

    key = "regions"
    requires = ("mesh",)

    def __init__(self, undo=None):
        super().__init__()
        self._undo = undo
        self.hidden_regions = self.observable("hidden_regions", [])
        self.boundary_overrides = self.observable("boundary_overrides", {})
        self.visibility = RegionVisibility()
        self.listeners = []

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.region_state = RegionState(self.context.base_data)
        view.region_visibility = self.visibility
        self.effect(self._push)

    def sync(self):
        """Bring the region state up to the observables (tracked)."""
        st = self.region_state
        st.hidden = set(self.hidden_regions.value)
        st.overrides = dict(self.boundary_overrides.value)
        return st

    def _push(self):
        st = self.sync()
        self.visibility.set_alphas(vol=st.vol_alphas(), surf=st.surf_alphas())
        for fn in self.listeners:
            fn()
        self.view.render()

    def applies(self):
        return len(self.region_state.unique_materials) > 1

    def bindings(self):
        return [
            Binding("h", self.hide_under_cursor, "Hide region under cursor", mode="g"),
            Binding("i", self.isolate_under_cursor, "Isolate region under cursor", mode="g"),
            Binding("a", self.show_all_regions, "Show all regions", mode="g"),
        ]

    # -- changes ---------------------------------------------------------

    def _record(self, label):
        if self._undo is None:
            return
        hidden = list(self.hidden_regions.value)
        overrides = dict(self.boundary_overrides.value)

        def restore():
            with batch():
                self.hidden_regions.value = hidden
                self.boundary_overrides.value = overrides
        self._undo(label, restore)

    def set_region_visible(self, name, visible):
        hidden = set(self.hidden_regions.value)
        if (name not in hidden) == bool(visible):
            return
        self._record(("show " if visible else "hide ") + name)
        if visible:
            hidden.discard(name)
        else:
            hidden.add(name)
        self.hidden_regions.value = sorted(hidden)

    def set_boundary_override(self, name, state):
        """state: True = force show, False = force hide, None = auto."""
        overrides = dict(self.boundary_overrides.value)
        if overrides.get(name) == state:
            return
        word = "auto" if state is None else ("show" if state else "hide")
        self._record(f"boundary {name}: {word}")
        if state is None:
            overrides.pop(name, None)
        else:
            overrides[name] = state
        self.boundary_overrides.value = overrides

    def show_all_regions(self):
        if not self.hidden_regions.value and not self.boundary_overrides.value:
            return
        self._record("show all")
        with batch():
            self.hidden_regions.value = []
            self.boundary_overrides.value = {}

    # -- under the cursor -------------------------------------------------

    def under_cursor(self):
        """Volume region of the last hover pick; on a boundary the visible
        adjacent one (hiding what one sees)."""
        picking = self.view.part("picking")
        result = picking.last if picking is not None else None
        if result is None:
            return None
        st = self.sync()
        if self.context.dim == 2 or result.kind in ("clipping", "volume"):
            return st.material_name(result.region_index)
        if result.kind == "surface":
            if result.region_index >= len(st.fd_doms):
                return None
            names = [st.material_name(d - 1) for d in st.fd_doms[result.region_index] if d >= 1]
            names = [n for n in names if n is not None]
            visible = [n for n in names if n not in st.hidden]
            return (visible or names or [None])[0]
        return None

    def hide_under_cursor(self):
        name = self.under_cursor()
        if name is not None:
            self.set_region_visible(name, False)

    def isolate_under_cursor(self):
        name = self.under_cursor()
        if name is None:
            return
        others = sorted(m for m in self.region_state.unique_materials if m != name)
        if others == sorted(self.hidden_regions.value):
            return
        self._record(f"isolate {name}")
        self.hidden_regions.value = others
