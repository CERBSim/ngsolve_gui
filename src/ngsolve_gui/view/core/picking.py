"""Hover picking: highlight of the entity under the pointer and the info card."""

from ngapp.components import Observable

from .part import Binding, Part
from ...pick_overlay import PickOverlay

_NONE = 0xFFFFFFFF


class Picking(Part):
    """Picks the pickable renderers of the layers on hover.

    ``result(event, kind)`` turns a select event into a pick result,
    ``info(result)`` gives ``(header, rows, accent_last)`` for the card. The
    handlers ``on_select(event, kind)``, ``on_out(ev)``, ``on_background(ev)``
    replace the default reaction (geometry selection does).
    With ``always`` the highlight cannot be switched off.
    """

    key = "picking"

    def __init__(self, result, info, *, always=False,
                 on_select=None, on_out=None, on_background=None):
        super().__init__()
        self.result, self.info, self.always = result, info, always
        self.on_select = on_select or self.select
        self.on_out = on_out or self.out
        self.on_background = on_background or self.background
        self.overlay = PickOverlay()
        self.highlights = []
        self.last = None
        self._pointer_inside = True
        self._shift = False
        self.enabled = None

    def attach(self, view):
        super().attach(view)
        if self.always:
            self.enabled = Observable(True, "picking_enabled")
        else:
            default = view.defaults.ref("picking_enabled", False, bool)
            self.enabled = Observable(default.value, "picking_enabled")
            self.enabled.on_change(lambda v, _o: setattr(default, "value", v))
        self.enabled.on_change(self._enabled_changed)

    def overlays(self):
        return [self.overlay]

    def bindings(self):
        if self.always:
            return []
        return [Binding("a", self.enabled.toggle, "Toggle highlight", mode="p")]

    def wire(self, scene):
        self.highlights = []
        for ro in scene.render_objects:
            for r in [ro, *getattr(ro, "render_objects", [])]:
                if hasattr(r, "_highlight_uniforms"):
                    self.highlights.append(r._highlight_uniforms)
        for layer in self.view.parts:
            for r, kind in getattr(layer, "pickables", lambda: [])():
                self.add(r, kind, highlight=False)
        scene.on_click_background(lambda ev: self.on_background(ev))
        scene.input_handler.on_mousemove(self._hover)
        scene.input_handler.on_mouseout(lambda ev: self._out(ev))

    def add(self, renderer, kind, highlight=True):
        """One more pickable renderer on the drawn scene."""
        if highlight and hasattr(renderer, "_highlight_uniforms"):
            self.highlights.append(renderer._highlight_uniforms)
        renderer.on_select(lambda ev, k=kind: self._select(ev, k))

    def _hover(self, ev):
        self._pointer_inside = True
        scene = self.view.scene
        if ev["buttons"] == 0 and scene.canvas is not None and scene.canvas.select_texture is not None:
            self._shift = ev.get("shiftKey", False)
            try:
                scene.select(ev["canvasX"], ev["canvasY"])
            except AttributeError:
                pass

    def _out(self, ev):
        self._pointer_inside = False
        self.on_out(ev)

    def _select(self, event, kind):
        # the readback of a hover pick can arrive after the pointer left the
        # view (e.g. onto the colorbar legend); its info would then stay up
        if self._pointer_inside:
            self.on_select(event, kind)

    # -- default reactions ------------------------------------------------

    def select(self, event, kind):
        try:
            result = self.result(event, kind)
            self.last = result
            header, rows, accent = self.info(result)
            if rows:
                self.overlay.show_info(header, rows, accent_last=accent)
            else:
                self.overlay.hide()
            if not self.enabled.value:
                return
            for hl in self.highlights:
                hl.renderer_id = event.obj_id
                if self._shift:
                    hl.element_id = _NONE
                    hl.region_index = result.region_index
                else:
                    hl.element_id = result.element_nr
                    hl.region_index = _NONE
                hl.update_buffer()
            self.view.scene._render_highlight()
        except Exception:
            self.overlay.hide()

    def out(self, ev):
        self.last = None
        self.clear_highlight()
        self.overlay.hide()
        self.view.render()

    def background(self, ev):
        self.last = None
        self.clear_highlight()
        self.overlay.hide()
        self.view.scene._render_highlight()

    def mark_regions(self, marks):
        """Mark regions, ``marks`` is ``{kind: region indices}``: pick kinds
        of the pickable renderers and ``mark_kind`` of parts; empty clears."""
        for part in self.view.parts:
            if getattr(part, "mark_kind", None) is not None:
                part.mark(marks.get(part.mark_kind, ()))
            for r, kind in getattr(part, "pickables", lambda: [])():
                if hasattr(r, "region_selection"):
                    r.region_selection.set(marks.get(kind, ()))
        if self.view.scene is not None:
            self.view.scene._render_highlight()

    def clear_highlight(self):
        for hl in self.highlights:
            hl.renderer_id = 0
            hl.element_id = _NONE
            hl.region_index = _NONE
            hl.solid_index = _NONE
            hl.update_buffer()

    def _enabled_changed(self, val, _old):
        if not val:
            self.clear_highlight()
            self.overlay.hide()
            self.view.render()
