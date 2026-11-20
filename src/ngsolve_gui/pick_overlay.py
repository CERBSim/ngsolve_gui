"""Floating pick-info card shown on hover/pick (designer style).

Hover fires on every mouse move: rows are keyed by their label, so a hover
over the same kind of entity only updates the value texts, and the visibility
class changes only on an actual show/hide (no fade restart, no flicker).
"""

from ngapp.components import Div, For, Observable, QIcon, computed

from . import cerbsim_style as cb
from .prop_widgets import on_cls

_TEXT = "_text"


class PickOverlay(Div):
    """Bottom-right card showing structured pick info (fades in/out)."""

    def __init__(self):
        self._header = Observable("", "pick_header")
        self._rows = Observable((), "pick_rows")  # (label, value, accent)
        self._visible = Observable(False, "pick_visible")

        def row(item):
            label = item.peek()[0]
            text = computed(lambda: str(item.value[1]))
            if label == _TEXT:
                return Div(text)
            value = Div(text, ui_class=computed(
                lambda: str(cb.pk_v_accent if item.value[2] else cb.pk_v)))
            return Div(Div(label), value, ui_class=str(cb.pk_r))

        header = Div(QIcon(ui_name="mdi-crosshairs"), Div(self._header), ui_class=str(cb.pk_h))
        super().__init__(
            header,
            Div(For(self._rows, row, key=lambda r: r[0], reactive=True)),
            ui_class=on_cls(cb.vp_pick, cb.vp_pick_visible, self._visible),
        )

    def show_info(self, header, rows, accent_last=False):
        """header: str; rows: list of (label, value). Last row may be accented."""
        n = len(rows)
        self._header.value = header
        self._rows.value = tuple(
            (k, v, accent_last and i == n - 1) for i, (k, v) in enumerate(rows))
        self._visible.value = True

    def show_text(self, text):
        """Single-line fallback (used by geometry picking)."""
        self._header.value = "Picked"
        self._rows.value = ((_TEXT, text, False),)
        self._visible.value = True

    def hide(self):
        self._visible.value = False
