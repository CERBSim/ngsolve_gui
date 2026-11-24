"""Vectors & Flow section for vector-valued functions.

Arrow glyphs can be drawn on the surface and/or on the clipping plane (3D);
those targets are toggle buttons in the section header so they can be switched
without opening the section. The body holds the arrow settings plus a grouped
"Flow" card bundling the streamlines (field-line) and LIC (line integral
convolution) sub-features. Only shown for vector CFs.
"""

from ngapp.components import *

from .. import cerbsim_style as cb
from ..prop_widgets import Section, Chip, Toggle, SubToggleBlock, chip_row, field
from ..cerbsim_style import gap_xs, gap_sm, gap_md, grow

_COL = "column " + str(gap_sm)


class VectorsFlowSection(Section):
    """Arrow glyphs (surface / clip plane) and streamlines for a vector field."""

    section_key = "vectors"

    def __init__(self, comp):
        self.comp = comp
        if comp.cf.dim <= 1:
            raise ValueError("Not applicable for scalar functions")

        part = comp.view.part
        style, lic, fieldlines = part("vector_style"), part("lic"), part("fieldlines")
        has_clip = part("clip_vectors").applies()

        # -- Header target toggles: where to draw the arrows (surface / clip). --
        head_actions = [
            Chip("Surface", "mdi-grid", part("surface_vectors").visible, small=True)
        ]
        if has_clip:
            head_actions.append(
                Chip("Clip", "mdi-box-cutter", part("clip_vectors").visible, small=True)
            )

        # -- Arrow settings (shared by both arrow targets) --
        self.grid_size = QInput(
            ui_type="number", ui_model_value=style.grid_size,
            ui_dense=True, ui_filled=True, ui_debounce=500,
        )

        self.vector_scale = QSlider(
            ui_model_value=style.scale, ui_min=0.1, ui_max=5.0, ui_step=0.1,
            ui_dense=True, ui_label=True, ui_class=grow,
        )
        # "Scale by magnitude" temporarily removed from the UI (not yet correct);
        # the field defaults to off (vector_scale_by_value)

        body = [
            field("Density", self.grid_size),
            field("Arrow scale", self.vector_scale),
        ]

        # -- Flow features: streamlines + LIC. Each sits in its own faint inset
        #    card (the shared card style signals they belong together) separated
        #    by a plain gap, and each toggle collapses its settings when off. --
        if fieldlines.applies():
            body.append(Div(self._build_streamlines(fieldlines), ui_class=cb.flow_group))
        if lic.applies():
            body.append(Div(self._build_lic(lic), ui_class=cb.flow_group))

        super().__init__(
            *body,
            icon="mdi-arrow-top-right-thin",
            title="Vectors & Flow",
            head_actions=head_actions,
            info="Draw the vector field as arrows on the surface and/or the "
                 "clipping plane (toggles in the header), or as streamlines.",
        )

    def _build_streamlines(self, fl):
        """Streamlines (field-line) sub-feature for the grouped flow card."""
        self.num_lines = QInput(ui_type="number", ui_model_value=fl.num_lines, ui_dense=True, ui_filled=True)
        self.length = QInput(ui_type="number", ui_model_value=fl.length, ui_dense=True, ui_filled=True)
        self.thickness = QInput(ui_type="number", ui_model_value=fl.thickness, ui_dense=True, ui_filled=True)
        self.direction = QSelect(
            ui_options=[{"label": "Both", "value": 0}, {"label": "Forward", "value": 1},
                        {"label": "Backward", "value": -1}],
            ui_model_value=fl.direction,
            ui_emit_value=True, ui_map_options=True, ui_dense=True, ui_filled=True,
        )
        self.recalc_btn = QBtn(
            ui_label="Recalculate", ui_icon="mdi-refresh", ui_color="primary",
            ui_outline=True, ui_dense=True, ui_no_caps=True, ui_size="sm",
            ui_class="full-width",
        )
        self.recalc_btn.on_click(lambda _: fl.recalculate())
        return SubToggleBlock(
            "Streamlines", fl.visible,
            Row(field("Lines", self.num_lines), field("Length", self.length),
                field("Thick.", self.thickness), ui_class="items-end no-wrap " + str(gap_xs)),
            field("Direction", self.direction),
            self.recalc_btn,
        )

    def _build_lic(self, lic):
        """Line Integral Convolution sub-feature for the grouped flow card.

        Paints the field's flow as a dense streamline texture — on the clipping
        plane (3D) or the surface itself (2D). Sliders two-way bind to the
        observables; the layer pushes them to the renderer."""
        kernel_length = QSlider(
            ui_model_value=lic.kernel_length, ui_min=5, ui_max=80, ui_step=1,
            ui_dense=True, ui_label=True,
        )
        contrast = QSlider(
            ui_model_value=lic.contrast, ui_min=0.0, ui_max=1.0, ui_step=0.05,
            ui_dense=True, ui_label=True,
        )
        # Line width is the droplet size, only meaningful in oriented mode — so it
        # sits next to the Oriented toggle and is disabled while oriented is off.
        oriented = Chip("Oriented", "mdi-arrow-right-thin", lic.oriented, small=True)
        thickness = QSlider(
            ui_model_value=lic.thickness, ui_min=1, ui_max=10, ui_step=1,
            ui_dense=True, ui_label=True, ui_class=grow,
            ui_disable=computed(lambda: not lic.oriented.value),
        )
        return SubToggleBlock(
            "Line integral convolution", lic.visible,
            field("Kernel length", kernel_length),
            field("Line width",
                  Row(thickness, oriented,
                      ui_class="items-center no-wrap " + str(gap_md))),
            field("Contrast", contrast),
            chip_row(
                Chip("Supersampling", "mdi-quality-high", lic.supersample, small=True),
            ),
        )
