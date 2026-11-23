"""Entity numbers section — show numeric labels on mesh entities."""

from ngapp.components import *

from ..prop_widgets import Section, Chip, chip_row, Toggle


class EntityNumbersSection(Section):
    section_key = "numbers"

    def __init__(self, comp):
        numbers = comp.view.part("numbers")
        if numbers is not None:
            entities, visible, one_based = numbers.entities, numbers.visible, numbers.one_based
        else:
            entities = comp.entity_number_entities
            visible = {e: getattr(comp, f"{e}_numbers_visible") for e in entities}
            one_based = comp.numbers_one_based
        chips = []
        for entity in entities:
            label = entity.replace("_", " ").title()
            label = label.replace("Surface Elements", "Surf. El.") \
                         .replace("Volume Elements", "Vol. El.") \
                         .replace("Surface Indices", "Surf. Idx") \
                         .replace("Segment Indices", "Seg. Idx") \
                         .replace("Volume Indices", "Vol. Idx")
            chips.append(Chip(
                label, observable=visible[entity], small=True,
            ))

        super().__init__(
            chip_row(*chips),
            Toggle("1-based indexing", one_based),
            icon="mdi-numeric",
            title="Numbers",
            info="Overlay entity index labels directly in the scene.",
        )

