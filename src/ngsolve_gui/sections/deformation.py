from ngapp.components import *

from ..prop_widgets import Section, Segmented, field


class DeformationSection(Section):
    section_key = "deformation"

    def __init__(self, comp):
        self.comp = comp
        deformation = comp.view.part("deformation")
        if deformation is None or not deformation.applies():
            raise ValueError("Deformation not applicable")

        self._deform_scale2 = QSlider(
            ui_model_value=deformation.scale2,
            ui_min=0.0, ui_max=1.0, ui_step=0.01, ui_dense=True, ui_label=True,
        )
        presets = Segmented(
            [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (5.0, "5×")],
            deformation.scale,
        )

        super().__init__(
            field("Scale", self._deform_scale2),
            presets,
            icon="mdi-arrow-expand-all",
            title="Deformation",
            switchable=True,
            observable=deformation.enabled,
            info="Warp the mesh by the displacement field to see how it deforms.",
        )
