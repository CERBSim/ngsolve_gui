"""Mesh generation section — meshing parameters and Create Mesh action.

Shown only in geometry scenes. Contains the numeric inputs for controlling
mesh generation and the action button to trigger it.
"""

from ngapp.components import *

from ..view.core.widgets import Section, field
from ..cerbsim_style import row2


def _positive_error(value):
    try:
        return "Must be positive" if value not in (None, "") and float(value) <= 0 else ""
    except (TypeError, ValueError):
        return ""


class MeshingInput(QInput):
    """A validated numeric input for meshing parameters."""

    def __init__(self, observable, **kwargs):
        self.observable = observable
        error = computed(lambda: _positive_error(observable.value))
        super().__init__(
            ui_model_value=observable,
            ui_type="number",
            ui_dense=True,
            ui_error=computed(lambda: bool(error.value)),
            ui_error_message=error,
            **kwargs,
        )


class MeshGenerationSection(Section):
    """Meshing parameters and Create Mesh button for geometry scenes."""

    section_key = "meshing"

    def __init__(self, comp):
        self.comp = comp

        meshing = comp.view.part("meshing")
        self.maxh = MeshingInput(meshing.maxh)
        self.segments = MeshingInput(meshing.segments_per_edge)
        self.curvature = MeshingInput(meshing.curvaturesafety)
        self.closeedge = MeshingInput(meshing.closeedgefac)

        self.create_btn = QBtn(
            ui_icon="mdi-vector-triangle",
            ui_label="Generate mesh",
            ui_color="primary",
            ui_no_caps=True,
            ui_class="full-width q-mt-xs",
        )
        self.create_btn.on_click(self._create_mesh)

        super().__init__(
            Div(
                field("Max mesh size", self.maxh),
                field("Segments / edge", self.segments),
                ui_class=row2,
            ),
            Div(
                field("Curvature safety", self.curvature),
                field("Close-edge fac.", self.closeedge),
                ui_class=row2,
            ),
            self.create_btn,
            icon="mdi-vector-triangle",
            title="Meshing",
            info="Generate a tetrahedral mesh from this geometry.",
        )

    def _create_mesh(self, *args):
        self.create_btn.ui_loading = True

        def _done():
            self.create_btn.ui_loading = False

        try:
            self.comp.create_mesh(on_done=_done)
        except Exception:
            self.create_btn.ui_loading = False
            raise
