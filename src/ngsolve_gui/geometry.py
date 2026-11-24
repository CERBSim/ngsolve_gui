from ngapp.components import *

from .tab import ViewTab
from .view.ngsolve.presets import geometry_view


class GeometryComponent(ViewTab):
    _picking_always_active = True

    def __init__(self, name, data, app_data):
        self.geo = data["obj"]
        super().__init__(name, data, app_data)

    def view_parts(self):
        return geometry_view(self.geo, **self.data)

    @property
    def clipping(self):
        return self.app_data.clipping

    @property
    def selection(self):
        return self.view.part("selection")

    @property
    def meshing(self):
        return self.view.part("meshing")

    @property
    def layer(self):
        return self.view.part("geometry")

    def create_mesh(self, on_done=None):
        """Mesh the geometry in a thread and open the mesh in a new tab."""
        from .mesh import MeshComponent
        from .meshing_preview import get_app
        from .workspace import identifier

        def on_mesh(mesh):
            title = "Mesh_" + self.title
            self.app_data.workspace.add(identifier(title), mesh)
            self.app_data.add_tab(title, MeshComponent, {"obj": mesh}, self.app_data)

        def on_error(msg):
            self.quasar.dialog({"title": "Error generating mesh", "message": msg})

        thread, done = self.meshing.generate(on_mesh, on_error, on_done)
        app = get_app()
        if app is not None:
            app.footer.show("mesh generation", thread, done)

    def property_subtitle(self):
        return "Geometry"

    def property_actions(self):
        return [{
            "label": "Download geometry", "icon": "mdi-download",
            "menu": [
                {"label": "STEP file (.step)", "icon": "mdi-file-outline",
                 "callback": lambda: self._download_geo("step")},
                {"label": "BREP file (.brep)", "icon": "mdi-file-outline",
                 "callback": lambda: self._download_geo("brep")},
                {"label": "Pickle file (.pkl)", "icon": "mdi-file-outline",
                 "callback": lambda: self._download_geo("pkl")},
            ],
        }]

    def _download_geo(self, fmt):
        import os, pickle, tempfile
        from .file_saver import save_file_dialog
        filename = (self.title or "geometry") + "." + fmt
        shape = self.geo.shape
        if fmt == "pkl":
            data = pickle.dumps(self.geo)
        else:
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, filename)
                if fmt == "step":
                    shape.WriteStep(path)
                else:
                    shape.WriteBrep(path)
                with open(path, "rb") as f:
                    data = f.read()
        save_file_dialog(data, filename)

    def draw(self):
        scene = self.view.draw()
        if scene is not None:
            self.clipping.center = 0.5 * (scene.bounding_box[1] + scene.bounding_box[0])

    def pick_handlers(self):
        return {"on_select": lambda ev, kind: self.selection.hover(ev, kind),
                "on_out": lambda ev: self.selection.out(ev),
                "on_background": lambda ev: self.selection.background(ev)}


# Register with the component registry
from .registry import register_component
from .sections import GeometryDisplaySection, GeometrySelectionSection, MeshGenerationSection

GeometryComponent.property_sections = [
    GeometryDisplaySection, GeometrySelectionSection, MeshGenerationSection,
]

register_component(
    "geometry",
    icon="mdi-cube",
    component_class=GeometryComponent,
)
