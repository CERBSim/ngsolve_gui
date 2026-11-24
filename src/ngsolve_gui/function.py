from ngapp.components import *
from .tab import ViewTab
from .view.ngsolve.presets import mesh_of, configure_function, function_view


def _fmt_value(v):
    """Fixed-width numeric format for the pick overlay.

    Scientific notation keeps very large/small magnitudes readable; fixed-point
    is used in the [1e-2, 1e2) range. The result is padded to a constant width
    so the value doesn't jitter horizontally as it updates while hovering.
    """
    v = float(v)
    a = abs(v)
    if a != 0 and (a < 1e-2 or a >= 1e2):
        s = f"{v: .4e}"   # e.g. ' 1.2345e+05' / '-1.2345e+05'
    else:
        s = f"{v: .5f}"   # e.g. ' 12.34567'
    return s.rjust(11)


class FunctionComponent(ViewTab):
    def __init__(self, name, data, app_data):
        self.app_data = app_data
        self.name = name
        self.cf = data["obj"]
        self.region_or_mesh = data["mesh"]
        self.mesh = mesh_of(self.region_or_mesh)
        super().__init__(name, data, app_data)

    def view_parts(self):
        return function_view(self.cf, self.region_or_mesh, undo=self.undo_stack.push,
                             **self.data)

    def configure(self):
        """Draw arguments win over the saved state."""
        configure_function(self.view, self.data)

    # -- parts --------------------------------------------------------------

    @property
    def deformation(self):
        return self.view.part("source").deformation_cf

    @property
    def colormap(self):
        return self.view.part("colormap").colormap

    @property
    def func_data(self):
        return self.view.part("field").data.value

    @property
    def mdata(self):
        return self.view.part("mesh").base_data

    def set_cf(self, cf, **options):
        """Show another function in this view."""
        self.cf = cf
        self.view.part("source").set_cf(cf, **options)

    def _pick_info(self, result):
        """Element / region / position / value — value uses the *undeformed*
        point so it stays correct when deformation is on."""
        header, rows, _ = super()._pick_info(result)
        val = self.view.part("field").evaluate(self._probe_mesh_point(result.world_pos))
        if val is not None:
            import numpy as np

            val = np.real(val)
            if val.size == 1:
                rows.append(("value", _fmt_value(val)))
            else:
                rows.append(("value", "[" + ", ".join(_fmt_value(v) for v in val.flat) + "]"))
            return ("Picked value", rows, True)
        return ("Picked value", rows, False)

    def property_subtitle(self):
        kind = "Vector" if self.cf.dim > 1 else "Scalar"
        return f"Function · {self.mesh.dim}D · {kind}"

    def property_xref(self):
        return {"label": "Open as mesh", "icon": "mdi-vector-triangle",
                "callback": self._open_as_mesh}

    def _build_viewport_legend(self):
        # The colorbar (colormap, range, autoscale, component) lives entirely in
        # the in-viewport legend now — not in the side panel.
        from .view.core.widgets import ColorbarLegend
        part = self.view.part
        return ColorbarLegend(part("colormap"), part("field"), lambda: self.title)

    def _open_as_mesh(self):
        from .mesh import MeshComponent
        self.app_data.add_tab(
            "Mesh_" + self.name, MeshComponent, {"obj": self.mesh}, self.app_data
        )

# Register with the component registry
from .registry import register_component
from .sections import (
    FunctionDisplaySection,
    DeformationSection,
    VectorsFlowSection,
    ComplexSection,
    EntityNumbersSection,
    RegionsSection,
)

FunctionComponent.property_sections = [
    FunctionDisplaySection,
    RegionsSection,
    DeformationSection,
    VectorsFlowSection,
    ComplexSection,
    EntityNumbersSection,
]

register_component(
    "function",
    icon="mdi-function-variant",
    component_class=FunctionComponent,
)
