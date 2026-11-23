"""Saved camera views."""

from ngapp.components import *

from .... import cerbsim_style as cb
from ..part import Part, Tool


class Bookmarks(Part):
    key = "bookmarks"

    def __init__(self):
        super().__init__()
        self.marks = Observable([], "bookmarks")  # (name, camera transform)
        self.open = Observable(False, "bookmarks_open")

    def tools(self):
        return [Tool(10, self._button, group=40)]

    def _button(self):
        def row(bookmark):
            name, snap = bookmark
            r = Div(QIcon(ui_name="mdi-camera-outline"), name, ui_class=str(cb.bm_row))
            r.on("click", lambda e=None: self.recall(snap))
            return r

        add = Div(QIcon(ui_name="mdi-plus"), "Save current view", ui_class=str(cb.bm_add))
        add.on("click", lambda e=None: self.save())
        pop = Div(
            Div("Saved views", ui_class=str(cb.bm_title)),
            For(self.marks, row, key=lambda b: b[0],
                otherwise=lambda: Div("No saved views", ui_class=str(cb.bm_empty))),
            add,
            ui_class=str(cb.bm_pop),
            ui_hidden=computed(lambda: not self.open.value),
        )
        pop.on("mouseleave", lambda e=None: setattr(self.open, "value", False))
        btn = Div(
            QIcon(ui_name="mdi-bookmark-outline"), self.view.dock_tip("Saved views"), pop,
            ui_class=str(cb.vp_tool) + " relative-position",
        )
        btn.on("click", lambda e=None: self.open.toggle())
        return btn

    def save(self):
        cam = self.view.scene.options.camera
        marks = self.marks.value
        self.marks.value = [*marks, (f"View {len(marks) + 1}", cam.transform.copy())]

    def recall(self, snap):
        cam = self.view.scene.options.camera
        cam.transform = snap.copy()
        cam._notify_observers()   # push the new camera uniform (as reset() does)
        self.view.render()
        self.open.value = False
