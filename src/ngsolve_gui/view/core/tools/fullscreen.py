"""Browser fullscreen of the viewport."""

from ..part import Part, Tool


class Fullscreen(Part):
    key = "fullscreen"

    def tools(self):
        return [Tool(0, lambda: self.view.tool_button(
            "mdi-fullscreen", "Fullscreen viewport", self.toggle), group=40)]

    def toggle(self):
        def go(js):
            try:
                el = self.view.scene.canvas.canvas.parentElement
                doc = js.document
                if doc.fullscreenElement is not None:
                    doc.exitFullscreen()
                else:
                    el.requestFullscreen()
            except Exception:
                pass
        self.view.call_js(go)
