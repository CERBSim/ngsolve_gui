from ngapp.components import *

from ..view.ngsolve.geometry import LABELS
from ..view.core.widgets import Section, PickPill, field
from ..cerbsim_style import chk_inline, field_label, gap_sm


class GeometrySelectionSection(Section):
    section_key = "selection"

    def __init__(self, comp):
        self.comp = comp
        sel = self.selection = comp.view.part("selection")
        self.context = comp.view.part("geometry_context")
        layer = comp.view.part("geometry")

        pick_row = Div(
            PickPill("S", sel.pick_solid, "Solids"),
            PickPill("F", sel.pick_faces, "Faces"),
            PickPill("E", sel.pick_edges, "Edges"),
            PickPill("V", sel.pick_vertices, "Vertices"),
            ui_class=chk_inline,
        )

        none = computed(lambda: not sel.items.value)
        # edit buffers, filled from the selection; edits reach the entities
        # through the input events only
        self.name = Observable("", "selection_name")
        self.maxh = Observable(None, "selection_maxh")
        self.name_hint = Observable("", "selection_name_hint")
        self.maxh_hint = Observable("", "selection_maxh_hint")
        sel.items.on_change(lambda items, _o: self._fill(items))

        def heading():
            items = sel.items.value
            if not items:
                return "No selection"
            if len(items) == 1:
                kind, index = items[0]
                return f"Selected: {LABELS.get(kind, kind)} {index}"
            return f"Selected: {len(items)} entities"

        self.meshsize_input = QInput(
            ui_type="number", ui_debounce=500, ui_dense=True, ui_disable=none,
            ui_model_value=self.maxh, ui_hint=self.maxh_hint,
            ui_error=computed(lambda: bool(sel.maxh_error.value)),
            ui_error_message=sel.maxh_error,
        )
        self.meshsize_input.on_update_model_value(lambda e: sel.set_maxh(e.value))
        self.name_input = QInput(
            ui_type="text", ui_debounce=500, ui_dense=True, ui_disable=none,
            ui_model_value=self.name, ui_hint=self.name_hint,
            ui_error=computed(lambda: bool(sel.name_error.value)),
            ui_error_message=sel.name_error,
        )
        self.name_input.on_update_model_value(lambda e: sel.set_name(e.value))

        hide_btn = QBtn("Hide", ui_icon="mdi-eye-off-outline", ui_outline=True,
                        ui_dense=True, ui_no_caps=True, ui_size="sm")
        hide_btn.on_click(lambda: layer.hide_selected())
        showall_btn = QBtn("Show all", ui_icon="mdi-eye-outline", ui_flat=True,
                           ui_dense=True, ui_no_caps=True, ui_size="sm")
        showall_btn.on_click(lambda: layer.show_all())

        super().__init__(
            field("Pick targets", pick_row),
            Div(computed(heading), ui_class=field_label),
            field("Local mesh size", self.meshsize_input),
            field("Name", self.name_input),
            Row(hide_btn, showall_btn, ui_class=gap_sm),
            icon="mdi-cursor-default-click",
            title="Selection",
            info="Pick entities in the scene to set local mesh size or rename them.",
        )

    def _entity_name_maxh(self, kind, index):
        entity = self.context.entity(kind, index)
        if entity is None:
            return ("", None)
        raw_maxh = entity.maxh
        return (entity.name or "", None if raw_maxh >= 1e99 else raw_maxh)

    def _fill(self, items):
        values = [self._entity_name_maxh(kind, idx) for kind, idx in items]
        names = {n for n, _ in values}
        maxhs = {h for _, h in values}
        multi = "Multiple values"
        self.name.value = names.pop() if len(names) == 1 else ""
        self.name_hint.value = multi if len(names) > 1 else ""
        self.maxh.value = maxhs.pop() if len(maxhs) == 1 else None
        self.maxh_hint.value = multi if len(maxhs) > 1 else ""
        if items:
            self.open.value = True
