from ngapp.components import *

import ngsolve as ngs

from .tab import ViewTab
from .view.core.layers.mesh import Elements2d, Elements3d, Identifications, Segments, Wireframe
from .view.core.layers.numbers import Numbers
from .view.core.modules.element_filter import ElementFilter
from .view.core.modules.regions import Regions
from .view.core.modules.subdivision import Subdivision, by_curve_order
from .view.ngsolve.mesh import Curvature, element_quality, mesh_context


class MeshComponent(ViewTab):
    def __init__(self, name, data, app_data):
        mesh = data["obj"]
        self.region_or_mesh = mesh
        self.mesh = mesh.mesh if isinstance(mesh, ngs.Region) else mesh
        self._quality = None
        super().__init__(name, data, app_data)
        self._pick_mesh = self.mesh

    def view_parts(self):
        data = self.data
        return [
            mesh_context(self.region_or_mesh),
            Curvature(self.mesh),
            Subdivision(data.get("subdivision"), auto=by_curve_order),
            ElementFilter(data.get("el2d_bitarray"), data.get("el3d_bitarray")),
            Regions(undo=self.undo_stack.push),
            Wireframe(), Elements2d(), Segments(), Identifications(), Elements3d(),
            Numbers(self.mesh.dim),
        ]

    @property
    def regions(self):
        return self.view.part("regions")

    @property
    def mesh_curvature_enabled(self):
        return self.view.part("curvature").enabled

    @property
    def mesh_curvature_order(self):
        return self.view.part("curvature").order

    def property_subtitle(self):
        return f"Mesh · {self.mesh.dim}D"

    def property_xref(self):
        return {"label": "Open geometry", "icon": "mdi-cube-outline",
                "callback": self._open_geometry}

    def property_actions(self):
        return [{"label": "Download mesh (.vol.gz)", "icon": "mdi-download",
                 "callback": self._download_mesh}]

    def _download_mesh(self):
        import os, tempfile
        from .file_saver import save_file_dialog
        filename = (self.title or "mesh") + ".vol.gz"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, filename)
            self.mesh.ngmesh.Save(path)
            with open(path, "rb") as f:
                data = f.read()
        save_file_dialog(data, filename)

    def _open_geometry(self):
        try:
            geo = self.mesh.ngmesh.GetGeometry()
            from .geometry import GeometryComponent
            self.app_data.add_tab(
                "Geo_" + self.title, GeometryComponent, {"obj": geo}, self.app_data
            )
        except Exception as e:
            print(f"Could not extract geometry from mesh: {e}")

    def element_quality(self):
        if self._quality is None:
            self._quality = element_quality(self.mesh)
        return self._quality

    def set_quality_threshold(self, threshold):
        """Show only the elements worse than ``threshold``; None shows all."""
        mask = None if threshold is None else self.element_quality() > threshold
        kind = "vol" if self.mesh.dim == 3 else "surf"
        self.view.part("element_filter").set("quality", kind, mask)


# Register with the component registry
from .registry import register_component
from .sections import MeshDisplaySection, MeshColorSection, EntityNumbersSection, RegionsSection

MeshComponent.property_sections = [
    MeshDisplaySection, RegionsSection, MeshColorSection, EntityNumbersSection,
]

register_component(
    "mesh",
    icon="mdi-vector-triangle",
    component_class=MeshComponent,
)
