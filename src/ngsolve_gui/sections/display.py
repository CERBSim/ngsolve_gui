"""Display sections — visibility toggles for each scene type.

Always the FIRST section, always expanded. Toggles are rendered as option chips
(designer look) bound directly to the component's visibility Observables.
"""

from ngapp.components import *

from ..prop_widgets import Section, Chip, chip_row, Toggle, field, MoreDisclosure
from ..cerbsim_style import prop_flab, input_tiny, gap_sm


class GeometryDisplaySection(Section):
    """Display section for geometry scenes."""

    section_key = "display"

    def __init__(self, comp):
        self.comp = comp
        chips = chip_row(
            Chip("Faces", "mdi-vector-square", comp.show_faces),
            Chip("Edges", "mdi-vector-line", comp.show_edges),
            Chip("Vertices", "mdi-vector-point", comp.show_vertices),
            Chip("Hover", "mdi-cursor-default-click", comp.picking_enabled),
        )
        super().__init__(chips, icon="mdi-eye", title="Display", opened=True)


class MeshDisplaySection(Section):
    """Display section for mesh scenes."""

    section_key = "display"

    def __init__(self, comp):
        self.comp = comp
        part = comp.view.part
        el3d = part("elements3d")

        chips = [
            Chip("Wireframe", "mdi-grid", part("wireframe").visible),
            Chip("Elements 2D", "mdi-triangle-outline", part("elements2d").visible),
        ]
        if el3d.applies():
            chips.append(Chip("Elements 3D", "mdi-cube-outline", el3d.visible))
        chips.append(Chip("Elements 1D", "mdi-vector-line", part("segments").visible))
        chips.append(Chip("Identifications", "mdi-link-variant", part("identifications").visible))
        chips.append(Chip("Hover", "mdi-cursor-default-click", comp.picking_enabled))

        shrink = QSlider(
            ui_model_value=el3d.shrink,
            ui_min=0.0, ui_max=1.0, ui_step=0.01, ui_label=True, ui_dense=True,
        )

        # Curved display: a master toggle plus the (disabled-until-on) order input.
        curvature = part("curvature")
        curve_order = QInput(
            ui_type="number", ui_model_value=curvature.order,
            ui_dense=True, ui_class=input_tiny,
            ui_disable=computed(lambda: not curvature.enabled.value),
        )

        subdivision = part("subdivision")
        subdiv = QInput(
            ui_type="number", ui_model_value=subdivision.value,
            ui_dense=True, ui_class=input_tiny,
        )

        advanced = [
            Toggle("Curved display", curvature.enabled),
            field("Curve order", curve_order),
            field(
                f"Subdivision (-1 auto, 0 linear, max {subdivision.MAX})",
                subdiv,
            ),
        ]

        if el3d.applies():
            subdiv3d = QInput(
                ui_type="number", ui_model_value=el3d.subdivision,
                ui_dense=True, ui_class=input_tiny,
            )
            advanced.append(field(
                f"3D subdivision (-1 auto, 0 linear, max {el3d.SUBDIVISION_MAX})",
                subdiv3d,
            ))

        items = [
            chip_row(*chips),
            field("Shrink", shrink),
            MoreDisclosure(*advanced, label_more="Advanced", label_less="Advanced"),
        ]

        super().__init__(*items, icon="mdi-eye", title="Display", opened=True)


class FunctionDisplaySection(Section):
    """Display section for function/solution scenes."""

    section_key = "display"

    def __init__(self, comp):
        self.comp = comp

        primary = [Chip("Wireframe", "mdi-grid", comp.wireframe_visible)]
        if comp.draw_surf:
            primary.append(Chip("Surface", "mdi-square-outline", comp.elements2d_visible))
        if comp.mesh.dim == 3 and comp.clippingcf is not None:
            primary.append(Chip("Clipping Fn", "mdi-box-cutter", comp.clipping_visible))
        # LIC is toggled inside the "Vectors & Flow" section (grouped with
        # streamlines), not as a top-level Display chip.
        primary.append(Chip("Highlight", "mdi-cursor-default-click", comp.picking_enabled))

        items = [chip_row(*primary)]

        subdiv = QInput(
            ui_type="number", ui_model_value=comp.subdivision,
            ui_dense=True, ui_class=input_tiny,
        )
        more_items = [field(
            f"Subdivision (-1 auto, 0 linear, max {comp.SUBDIVISION_MAX})",
            subdiv,
        )]

        chips_adv = []
        if comp._facet_supported:
            chips_adv.append(Chip("ElementBND", "mdi-vector-polyline", comp.facet_visible))
        if comp.contact is not None:
            chips_adv.append(Chip("Contact Pairs", "mdi-vector-intersection", comp.contact_enabled))
        if chips_adv:
            more_items.append(chip_row(*chips_adv))
        if comp._facet_supported:
            thickness = QSlider(
                ui_model_value=comp.facet_thickness,
                ui_min=0.001, ui_max=0.05, ui_step=0.001, ui_dense=True, ui_label=True,
            )
            more_items.append(field("ElementBND thickness", thickness))

        items.append(MoreDisclosure(
            *more_items, label_more="Advanced", label_less="Advanced"))

        super().__init__(*items, icon="mdi-eye", title="Display", opened=True)
