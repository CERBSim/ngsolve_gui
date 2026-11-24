from ngapp.components import *
from ngsolve_webgpu import *
from .settings import usersettings as _usersettings
from .tab import ViewTab
from .view.core import Layer
from .view.core.layers.field import ClipField, Surface
from .view.core.layers.mesh import Edges, Wireframe
from .view.core.layers.numbers import Numbers
from .view.core.modules.colormap import Colormap as ColormapPart
from .view.core.modules.complex import Complex
from .view.core.modules.deformation import Deformation
from .view.core.modules.field import Field
from .view.core.modules.regions import Regions
from .view.core.modules.subdivision import Subdivision
from .view.core.part import mark
from .view.ngsolve.field import FieldSource
from .view.ngsolve.mesh import mesh_context
import ngsolve as ngs


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


def _positive_int(value):
    value = int(float(value))
    if value < 1:
        raise ValueError(value)
    return value


class _Legacy(Layer):
    """Renderers of the function tab not split into layers yet (facet,
    vectors, LIC, field lines, contact); built by the tab."""

    key = "legacy"
    order = 50
    requires = ("mesh", "field", "colormap")

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        # the facet renderer is expensive: built once it is first shown
        self.facet_wanted = Observable(tab.facet_visible.value, "facet_wanted")

    def attach(self, view):
        super().attach(view)
        self.context = view.part("mesh")
        self.field = view.part("field")

    def build(self):
        self.context.revision.value
        data, clipping = self.field.data.value, self.view.clipping
        facet = self.facet_wanted.value
        if data is None:
            return []
        with untracked():
            return self.tab._build_legacy(data, clipping, facet)

    def pickables(self):
        lic = self.tab.lic
        return [(lic, "surface")] if lic is not None and self.tab._lic_is_surface else []

    def suppresses(self, key):
        # a surface LIC replaces the flat surface field
        return key == "surface" and self.tab._lic_is_surface and self.tab.lic_visible.value


class FunctionComponent(ViewTab):
    SUBDIVISION_MAX = 40

    def __init__(self, name, data, app_data):
        self.app_data = app_data
        cf = data["obj"]
        self.name = name
        self.cf = cf
        self.region_or_mesh = data["mesh"]
        self.draw_vol = data.get("draw_vol", True)
        self.draw_surf = data.get("draw_surf", True)
        self.draw_edges = data.get("edges", False)
        self.mesh = (
            self.region_or_mesh.mesh
            if isinstance(self.region_or_mesh, ngs.Region)
            else self.region_or_mesh
        )
        self.facet = data.get("facet", None)
        self.contact = data.get("contact", None)
        self.contact_pairs = None
        self.facet_renderer = None
        self.surface_vectors = None
        self.clipping_vectors = None
        self.fieldlines = None
        self.lic = None
        self._lic_is_surface = False
        self._facet_supported = bool(self.draw_vol) and self.mesh.dim in (2, 3)

        saved = app_data.saved_settings()
        cv = data.get("clipping_vectors", False)
        sv = data.get("surface_vectors", False)
        fl = data.get("field_lines", False)
        lic = data.get("lic", False)

        s = saved
        self.facet_visible = Observable(
            bool(self.facet) if self.facet is not None else s.get("facet_visible", False),
            "facet_visible",
        )
        self.facet_thickness = Observable(
            s.get("facet_thickness", 0.008), "facet_thickness", converter=float
        )
        self.clipping_vectors_visible = Observable(
            bool(cv) if cv else s.get("clipping_vectors", False), "clipping_vectors"
        )
        self.surface_vectors_visible = Observable(
            bool(sv) if sv else s.get("surface_vectors", False), "surface_vectors"
        )
        self.field_lines_visible = Observable(
            bool(fl) if fl else s.get("field_lines", False), "field_lines"
        )
        # -- LIC (line integral convolution) on the clipping plane --
        self.lic_visible = Observable(
            bool(lic) if lic else s.get("lic_visible", False), "lic_visible"
        )
        self.lic_kernel_length = Observable(
            s.get("lic_kernel_length", 30), "lic_kernel_length", converter=int
        )
        self.lic_oriented = Observable(
            s.get("lic_oriented", False), "lic_oriented"
        )
        self.lic_thickness = Observable(
            s.get("lic_thickness", 2), "lic_thickness", converter=int
        )
        self.lic_contrast = Observable(
            s.get("lic_contrast", 1.0), "lic_contrast", converter=float
        )
        # Supersampling (SSAA) checkbox: off → 1 sample, on → 2 samples.
        self.lic_supersample = Observable(
            s.get("lic_supersample", False), "lic_supersample"
        )
        self.vector_grid_size = Observable(
            (cv if not isinstance(cv, bool) else None)
            or (sv if not isinstance(sv, bool) else None)
            or s.get("vector_grid_size", int(_usersettings.get("default_vector_grid_size", 20))),
            "vector_grid_size", converter=_positive_int,
        )
        self.vector_scale = Observable(
            s.get("vector_scale", 1.0), "vector_scale", converter=float
        )
        self.vector_scale_by_value = Observable(
            s.get("vector_scale_by_value", False), "vector_scale_by_value",
        )
        self.contact_enabled = Observable(
            s.get("contact_enabled", True), "contact_enabled"
        )
        self.fieldlines_num_lines = Observable(
            s.get("fieldlines_num_lines", data.get("fieldlines_num_lines", 100)), "fieldlines_num_lines", converter=int
        )
        self.fieldlines_length = Observable(
            s.get("fieldlines_length", data.get("fieldlines_length", 0.5)), "fieldlines_length", converter=float
        )
        self.fieldlines_thickness = Observable(
            s.get("fieldlines_thickness", data.get("fieldlines_thickness", 0.0015)), "fieldlines_thickness", converter=float
        )
        self.fieldlines_direction = Observable(
            s.get("fieldlines_direction", 0), "fieldlines_direction", converter=int
        )

        super().__init__(name, data, app_data)
        self._pick_mesh = self.mesh
        self.view.part("regions").listeners.append(
            lambda: self.lic is not None and self.lic._refresh())

        self.facet_visible.on_change(self._apply_facet)
        self.facet_thickness.on_change(self._apply_facet_thickness)
        self.clipping_vectors_visible.on_change(self._apply_clipping_vectors)
        self.surface_vectors_visible.on_change(self._apply_surface_vectors)
        self.field_lines_visible.on_change(self._apply_fieldlines)
        self.lic_visible.on_change(self._apply_lic)
        self.lic_kernel_length.on_change(self._apply_lic_kernel_length)
        self.lic_oriented.on_change(self._apply_lic_oriented)
        self.lic_thickness.on_change(self._apply_lic_thickness)
        self.lic_contrast.on_change(self._apply_lic_contrast)
        self.lic_supersample.on_change(self._apply_lic_supersample)
        self.vector_grid_size.on_change(self._apply_vector_grid_size)
        self.vector_scale.on_change(self._apply_vector_scale)
        self.vector_scale_by_value.on_change(self._apply_vector_scale_by_value)
        self.contact_enabled.on_change(self._apply_contact)

    def view_parts(self):
        data = self.data
        parts = [
            mesh_context(self.region_or_mesh),
            Subdivision(data.get("subdivision"), max=self.SUBDIVISION_MAX),
            Regions(undo=self.undo_stack.push),
            Field(), Deformation(), Complex(), ColormapPart(),
            FieldSource(self.cf, self.region_or_mesh, order=data.get("order"),
                        labels=data.get("component_labels"),
                        deformation=data.get("deformation"),
                        deformation_order=data.get("deformation_order")),
            Wireframe(visible=data.get("wireframe")),
            Surface(enabled=bool(self.draw_surf)),
            ClipField(enabled=bool(self.draw_vol)),
        ]
        if self.draw_edges:
            parts.append(Edges(None if isinstance(self.draw_edges, bool) else self.draw_edges))
        parts += [_Legacy(self), Numbers(self.mesh.dim)]
        return parts

    def configure(self):
        """Draw arguments win over the saved state."""
        data, part = self.data, self.view.part
        if "deformation" in data and part("deformation").applies():
            part("deformation").enabled.value = True
        if "clipping_function" in data:
            part("clipfield").visible.value = bool(data["clipping_function"])
        colormap = part("colormap")
        if any(k in data for k in ("min", "max", "autoscale")):
            colormap.autoscale.value = data.get(
                "autoscale", not ("min" in data or "max" in data))
        if "min" in data:
            colormap.min.value = data["min"]
        if "max" in data:
            colormap.max.value = data["max"]
        if "discrete_colormap" in data:
            colormap.discrete.value = bool(data["discrete_colormap"])

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

    # -- renderers not split into layers yet --------------------------------

    def _build_legacy(self, func_data, clipping, facet):
        """Facet, vector, LIC, field line and contact renderers."""
        mdata = func_data.mesh_data
        colormap = self.colormap
        cf, order, region = self.cf, self.view.part("source").order, self.region_or_mesh
        self.surface_vectors = self.clipping_vectors = self.lic = self.fieldlines = None
        self.facet_renderer = None
        # a SurfaceLIC (2D) replaces the flat surface field, a ClippingLIC (3D)
        # overlays the cutting plane
        self._lic_is_surface = False
        lic_args = dict(
            clipping=clipping, colormap=colormap,
            kernel_length=self.lic_kernel_length.value, oriented=self.lic_oriented.value,
            thickness=self.lic_thickness.value, contrast=self.lic_contrast.value,
            supersample=2 if self.lic_supersample.value else 1)
        vector_args = dict(
            clipping=clipping, colormap=colormap, grid_size=self.vector_grid_size.value,
            scale_by_value=self.vector_scale_by_value.value)
        if cf.dim == self.mesh.dim:
            vec3 = cf if cf.dim == 3 else ngs.CF((cf[0], cf[1], 0))
            vec_data = self.app_data.get_function_gpu_data(vec3, region, order=order)
            self.surface_vectors = mark(SurfaceVectors(vec_data, **vector_args), "complex")
            self.surface_vectors.user_scale = self.vector_scale.value
            self.surface_vectors.active = self.surface_vectors_visible.value
            if self.mesh.dim == 2:
                self.lic = SurfaceLIC(vec_data, **lic_args)
                self._lic_is_surface = True
            from ngsolve_webgpu.cf import FieldLines

            self.fieldlines = FieldLines(
                vec3, region,
                num_lines=self.fieldlines_num_lines.value,
                length=self.fieldlines_length.value,
                thickness=self.fieldlines_thickness.value,
                direction=self.fieldlines_direction.value,
                colormap=colormap, clipping=clipping,
            )
            self.fieldlines.active = self.field_lines_visible.value
        if self.mesh.dim == 3 and self.draw_vol and cf.dim == 3:
            self.clipping_vectors = mark(ClippingVectors(func_data, **vector_args), "complex")
            self.clipping_vectors.user_scale = self.vector_scale.value
            self.clipping_vectors.active = self.clipping_vectors_visible.value
            self.lic = ClippingLIC(func_data, **lic_args)
        if self.lic is not None:
            mark(self.lic, "component", "complex")
            self.lic.active = self.lic_visible.value
        if facet:
            self._create_facet_renderer(mdata, clipping, colormap)
        if self.contact is not None:
            from ngsolve_webgpu.contact import ContactPairs
            from webgpu.renderer import MultipleRenderer

            if isinstance(self.contact, list):
                from .region_colors import get_random_colors

                colors = get_random_colors(len(self.contact))
                self.contact_pairs = MultipleRenderer(
                    [ContactPairs(region, c, color=col) for c, col in zip(self.contact, colors)])
            else:
                self.contact_pairs = ContactPairs(region, self.contact)
            self.contact_pairs.active = self.contact_enabled.value
        return [r for r in (self.lic, self.facet_renderer, self.contact_pairs,
                            self.clipping_vectors, self.surface_vectors, self.fieldlines)
                if r is not None]

    def _create_facet_renderer(self, mdata, clipping, colormap):
        """Extracting the CF on all element boundaries is expensive, so this
        only runs once element boundaries are switched on."""
        if not self._facet_supported:
            return None
        order = self.view.part("source").order
        facet_cf = (
            self.facet if isinstance(self.facet, ngs.CoefficientFunction) else self.cf
        )
        try:
            if self.mesh.dim == 2:
                # deformation is baked in unconditionally; the deformation_scale
                # uniform (0 when disabled) switches it on and off
                facet_data = FacetFunctionData(
                    mdata, facet_cf, order=order, deformation_cf=self.deformation,
                )
                self.facet_renderer = FacetCFRenderer(
                    facet_data, colormap=colormap, clipping=clipping,
                    thickness=self.facet_thickness.value,
                )
            else:
                from ngsolve_webgpu.facet_cf import FacetCFRenderer3D

                self.facet_renderer = FacetCFRenderer3D(
                    mdata, facet_cf, order=order, colormap=colormap, clipping=clipping,
                )
        except Exception as e:
            import traceback
            print(f"Warning: facet renderer creation failed: {e}")
            traceback.print_exc()
            self.facet_renderer = None
            return None
        mark(self.facet_renderer, "deformation")
        self.facet_renderer.active = self.facet_visible.value
        return self.facet_renderer

    def _apply_facet(self, visible, _old):
        if visible:
            self.view.part("legacy").facet_wanted.value = True
        if self.facet_renderer is not None:
            self.facet_renderer.active = visible
            self.view.render()

    def _apply_facet_thickness(self, val, _old):
        if self.facet_renderer is not None:
            self.facet_renderer.thickness = val
            self.facet_renderer.set_needs_update()
            self.wgpu.scene.render()

    def _apply_clipping_vectors(self, val, _old):
        if self.clipping_vectors is not None:
            self.clipping_vectors.active = val
        self.wgpu.scene.render()

    def _apply_surface_vectors(self, val, _old):
        if self.surface_vectors is not None:
            self.surface_vectors.active = val
        self.wgpu.scene.render()

    def _apply_fieldlines(self, val, _old):
        if self.fieldlines is not None:
            self.fieldlines.active = val
        self.wgpu.scene.render()

    def _apply_lic(self, val, _old):
        if self.lic is not None:
            self.lic.active = val
        self.wgpu.scene.render()

    def _apply_lic_kernel_length(self, val, _old):
        if self.lic is not None:
            self.lic.set_kernel_length(val)
        self.wgpu.scene.render()

    def _apply_lic_oriented(self, val, _old):
        if self.lic is not None:
            self.lic.set_oriented(val)
        self.wgpu.scene.render()

    def _apply_lic_thickness(self, val, _old):
        if self.lic is not None:
            self.lic.set_thickness(val)
        self.wgpu.scene.render()

    def _apply_lic_contrast(self, val, _old):
        if self.lic is not None:
            self.lic.set_contrast(val)
        self.wgpu.scene.render()

    def _apply_lic_supersample(self, val, _old):
        if self.lic is not None:
            # Checkbox toggles between 1 (off) and 2 (on) samples per pixel.
            self.lic.set_supersample(2 if val else 1)
        self.wgpu.scene.render()

    def _apply_vector_grid_size(self, val, _old):
        if self.clipping_vectors is not None:
            self.clipping_vectors.set_grid_size(val)
            self.clipping_vectors.set_needs_update()
        if self.surface_vectors is not None:
            self.surface_vectors.set_grid_size(val)
            self.surface_vectors.set_needs_update()
        self.wgpu.scene.render()

    def _apply_vector_scale(self, val, _old):
        for r in self._vector_renderers:
            r.user_scale = val
            r.set_needs_update()
        self.wgpu.scene.render()

    def _apply_vector_scale_by_value(self, val, _old):
        for r in self._vector_renderers:
            r.scale_by_value = val
            r.set_needs_update()
        self.wgpu.scene.render()

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

    def _apply_contact(self, val, _old):
        if self.contact_pairs is not None:
            self.contact_pairs.active = val
        self.wgpu.scene.render()

    # -- Keybinding support -------------------------------------------------

    def tab_keybindings(self):
        """Bindings of the renderers not split into layers yet."""
        show = []
        if self._facet_supported:
            show.append(("e", self.toggle_facet, "Toggle element boundaries"))
        if self.surface_vectors is not None:
            show.append(("v", self.toggle_surface_vectors, "Toggle surface vectors"))
        if self.clipping_vectors is not None:
            show.append(("c", self.toggle_clipping_vectors, "Toggle clipping vectors"))
        if self.lic is not None:
            show.append(("l", self.toggle_lic, "Toggle LIC"))
        if self.fieldlines is not None:
            show.append(("f", self.toggle_fieldlines, "Toggle field lines"))
        if self.surface_vectors is not None or self.clipping_vectors is not None:
            show.append(("+", self.increase_vector_density, "Increase vector density"))
            show.append(("-", self.decrease_vector_density, "Decrease vector density"))
        modes = [("s", "Show", show)]
        if self.mesh.dim == 3 and self.lic is not None:
            modes.append(("c", "Clipping", [("l", self.toggle_lic, "Toggle LIC")]))
        return {"flat": [], "modes": modes}

    def toggle_facet(self):
        self.facet_visible.toggle()

    def toggle_clipping_vectors(self):
        self.clipping_vectors_visible.toggle()

    def toggle_surface_vectors(self):
        self.surface_vectors_visible.toggle()

    def toggle_fieldlines(self):
        self.field_lines_visible.toggle()

    def toggle_lic(self):
        self.lic_visible.toggle()

    def _change_vector_density(self, factor):
        grid_size = max(10, int(self.vector_grid_size.value * factor))
        self.vector_grid_size.value = grid_size

    def increase_vector_density(self):
        self._change_vector_density(1.25)

    def decrease_vector_density(self):
        self._change_vector_density(0.8)

    @property
    def _vector_renderers(self):
        return [r for r in [self.clipping_vectors, self.surface_vectors] if r is not None]

    def property_subtitle(self):
        kind = "Vector" if self.cf.dim > 1 else "Scalar"
        return f"Function · {self.mesh.dim}D · {kind}"

    def property_xref(self):
        return {"label": "Open as mesh", "icon": "mdi-vector-triangle",
                "callback": self._open_as_mesh}

    def _build_viewport_legend(self):
        # The colorbar (colormap, range, autoscale, component) lives entirely in
        # the in-viewport legend now — not in the side panel.
        from .prop_widgets import ColorbarLegend
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
