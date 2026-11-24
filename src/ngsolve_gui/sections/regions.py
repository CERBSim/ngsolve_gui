"""Regions section — per-region draw visibility for function scenes.

Volume regions (materials) get plain visibility checkboxes; surfaces follow
automatically through the mesh adjacency (an interface stays visible while
either adjacent volume region is visible — see ``ngsolve_webgpu.region_visibility.RegionState``).
Per-boundary overrides live behind a "Boundaries" disclosure: each boundary
cycles auto → hidden → shown, and its label dims when it is currently not
drawn (whether by override or derivation).
"""

from ngapp.components import *

from ..prop_widgets import Section, MoreDisclosure
from ..cerbsim_style import field_label, region_item_row


class RegionsSection(Section):
    section_key = "regions"

    _BND_CYCLE = {None: False, False: True, True: None}
    _BND_TEXT = {None: "auto", False: "off", True: "on"}

    def __init__(self, comp):
        self.comp = comp
        self.regions = comp.view.part("regions")
        st = self.regions.region_state
        mats = st.unique_materials
        bnds = st.unique_boundaries if comp.mesh.dim == 3 else []
        if len(mats) <= 1 and len(bnds) <= 1:
            raise ValueError("no regions to manage")

        self._filter = Observable("", "region_filter")

        show_all = QBtn(
            QTooltip("Show all regions"),
            ui_icon="mdi-eye-refresh-outline", ui_flat=True, ui_dense=True,
            ui_round=True, ui_size="sm",
        )
        show_all.on_click(lambda e=None: self.regions.show_all_regions())

        super().__init__(
            icon="mdi-layers-outline", title="Regions",
            opened=bool(st.any_hidden()), head_actions=[show_all],
        )
        # rows are built on first open: meshes with many regions would
        # otherwise send thousands of components for every new tab
        self._body.ui_children = [Show(self.open, lambda: self._rows(mats, bnds))]

    def _state(self):
        """The region state for the current observables (tracked)."""
        return self.regions.sync()

    def _rows(self, mats, bnds):
        rows = []
        if len(mats) + len(bnds) > 10:
            rows.append(QInput(
                ui_label="Filter...", ui_dense=True, ui_clearable=True,
                ui_debounce=300, ui_class="q-mb-xs", ui_model_value=self._filter,
            ))
        rows += [self._mat_row(name) for name in mats]
        if bnds:
            hint = Div(
                "auto: drawn while an adjacent volume region is visible",
                ui_class=field_label,
            )
            rows.append(MoreDisclosure(
                hint, *[self._bnd_row(name) for name in bnds],
                label_more="Boundaries", label_less="Boundaries"))
        return rows

    def _row(self, name, control, label):
        row = Div(
            Div(control, ui_class="col-auto"),
            Div(label, ui_class="col " + field_label + " ellipsis"),
            ui_class="row items-center no-wrap " + region_item_row,
        )
        lower = name.lower()
        row.ui_hidden = computed(
            lambda: bool(self._filter.value) and self._filter.value.lower().strip() not in lower)
        return row

    def _mat_row(self, name):
        regions = self.regions
        vis = QCheckbox(
            ui_dense=True,
            ui_model_value=computed(lambda: name not in regions.hidden_regions.value),
        )
        vis.on_update_model_value(lambda e: regions.set_region_visible(name, bool(e.value)))
        return self._row(name, vis, Label(name))

    def _bnd_row(self, name):
        regions = self.regions
        override = computed(lambda: regions.boundary_overrides.value.get(name))
        btn = QBtn(
            QTooltip("Cycle auto / off / on"),
            ui_label=computed(lambda: self._BND_TEXT[override.value]),
            ui_flat=True, ui_dense=True, ui_size="sm", ui_no_caps=True,
        )
        btn.on_click(lambda e=None: regions.set_boundary_override(
            name, self._BND_CYCLE[override.value]))
        label = Label(name, ui_style=computed(
            lambda: "" if self._state().boundary_effective(name) else "opacity: 0.45;"))
        return self._row(name, btn, label)
