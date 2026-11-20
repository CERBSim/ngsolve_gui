import numpy as np
from ngapp.components import *
from ngsolve_gui.region_colors import RegionColors
from ..prop_widgets import Section, Segmented, on_cls
from ..cerbsim_style import (
    gap_sm, grow, mono, hint, muted, prop_switch, prop_switch_on, qhist_col,
)


class MeshColorSection(Section):
    """Coloring / visibility, switchable between modes:
    ``By region`` keeps the grouped region colors; ``By quality`` isolates the
    worst elements by Jacobian condition number; ``By element type`` (3D only)
    toggles visibility per element type (boundary-layer prisms, closure pyramids)."""

    section_key = "colors"

    def __init__(self, comp):
        self.comp = comp
        builders = {"region": self._build_region, "quality": self._build_quality}
        options = [("region", "By region"), ("quality", "By quality")]
        if comp.mesh.dim == 3:
            builders["eltype"] = self._build_eltype
            options.append(("eltype", "By element type"))

        # The segment just chooses which controls are shown; the region (alpha),
        # element-type and quality filters compose and stay applied across modes.
        mode = Observable("region", "color_mode")
        boxes = [Show(computed(lambda k=key: mode.value == k), lambda b=build: b(comp))
                 for key, build in builders.items()]
        seg = Segmented(options, mode, self._mode_selected)
        super().__init__(seg, *boxes, icon="mdi-palette", title="Coloring")

    def _mode_selected(self, val):
        if val in ("eltype", "quality") and self.comp.mesh.dim == 3:
            # show the volume mesh so volume-element filtering is visible
            self.comp.elements3d_visible.value = True

    # -- By region (grouped region colors) --------------------------------
    def _build_region(self, comp):
        colors = [(c[0], c[1], c[2], c[3]) for c in
                  (fd.color for fd in comp.mesh.ngmesh.FaceDescriptors())]
        names = [fd.bcname for fd in comp.mesh.ngmesh.FaceDescriptors()]
        face_colors = RegionColors("Face Colors", colors, names)
        face_colors.on_change_color(self.change_color)
        cards = [QCard(QCardSection(face_colors), ui_flat=True, ui_bordered=True)]

        edge_descriptors = list(comp.mesh.ngmesh.EdgeDescriptors())
        if edge_descriptors:
            enames = [ed.name for ed in edge_descriptors]
            saved = comp.edge_colors.value
            self.ecolors = {name: saved.get(name, [0, 0, 0, 255]) for name in set(enames)}
            ecolors = [
                (c[0] / 255, c[1] / 255, c[2] / 255, c[3] / 255 if c[3] > 1 else c[3])
                for c in [self.ecolors[name] for name in enames]
            ]
            edge_colors = RegionColors("Edge Colors", ecolors, enames)
            edge_colors.on_change_color(self.change_edge_color)
            cards.append(QCard(QCardSection(edge_colors), ui_flat=True, ui_bordered=True))

        if comp.mesh.dim == 3:
            dnames = list(set(comp.mesh.GetMaterials()))
            dcolors = [(1.0, 0.0, 0.0, 1.0) for _ in range(len(dnames))]
            domain_colors = RegionColors("Domain Colors", dcolors, dnames)
            self.dcolors = {name: [int(255 * ci) for ci in dcol]
                            for name, dcol in zip(dnames, dcolors)}
            domain_colors.on_change_color(self.change_d_color)
            cards.append(QCard(QCardSection(domain_colors), ui_flat=True, ui_bordered=True))

        return Div(*cards, ui_class="column " + str(gap_sm))

    # -- By element type (3D visibility) ----------------------------------
    _TYPE_LABELS = {
        "ET.TET": "Tetrahedra",
        "ET.PRISM": "Prisms · boundary layer",
        "ET.PYRAMID": "Pyramids · closure",
        "ET.HEX": "Hexahedra",
    }

    def _build_eltype(self, comp):
        types = comp.element_types_3d()
        visible = Observable(frozenset(types), "visible_element_types")
        visible.on_change(lambda v, _o: comp.set_visible_element_types(set(v)))
        rows = [self._type_row(visible, et, count) for et, count in types.items()]
        return Div(*rows, ui_class="column " + str(gap_sm))

    def _type_row(self, visible, et, count):
        label = self._TYPE_LABELS.get(str(et), str(et))
        sw = Div(ui_class=on_cls(prop_switch, prop_switch_on,
                                 computed(lambda: et in visible.value)))
        sw.on("click", lambda e=None: setattr(visible, "value", visible.value ^ {et}))
        return Div(
            Div(label, ui_class=str(grow)),
            Div(str(count), ui_class=str(mono) + " " + str(hint)),
            sw,
            ui_class="row items-center no-wrap " + str(gap_sm),
        )

    # -- By quality (Jacobian condition number) ---------------------------
    def _build_quality(self, comp):
        q = comp.element_quality()
        qmin, qmax = float(np.min(q)), float(np.max(q))
        total = len(q)
        isolate = Observable(False, "quality_isolate")
        thr = Observable(float(np.percentile(q, 90)), "quality_threshold")  # worst ~10%

        def apply(*_):
            comp.set_quality_threshold(thr.value if isolate.value else None)
        isolate.on_change(apply)
        thr.on_change(lambda v, _o: isolate.value and apply())

        stats = Div(
            Div(f"best {qmin:.2f}"),
            Div(f"median {float(np.median(q)):.2f}"),
            Div(f"worst {qmax:.2f}"),
            ui_class="row " + str(gap_sm) + " " + str(mono) + " " + str(hint),
        )

        # log-binned histogram when the range spans more than a factor of 3
        nbins = 22
        log = qmax > qmin * 3
        if qmax <= qmin:
            edges = np.array([qmin, qmin + 1.0])
        elif log:
            edges = np.logspace(np.log10(qmin), np.log10(qmax), nbins + 1)
        else:
            edges = np.linspace(qmin, qmax, nbins + 1)
        counts, _ = np.histogram(q, bins=edges)
        cmax = max(1, int(counts.max()))

        def select_bin(i):
            # isolate that bin and everything worse (to its right)
            thr.value = float(edges[i])
            isolate.value = True

        bars = []
        for i, c in enumerate(counts):
            pos = i / (len(counts) - 1) if len(counts) > 1 else 0.0
            hue = 140 * (1 - pos)               # green (good) → red (bad)
            h = 5 + 39 * (c / cmax)
            fill = Div(ui_style=(
                f"width:100%; height:{h:.0f}px; border-radius:2px;"
                f" background:hsl({hue:.0f},62%,55%);"
            ))
            # The whole column is clickable so even 1-element bars are easy to hit.
            col = Div(QTooltip(f"cond ≥ {edges[i]:.2f} · {int(c)} here"), fill,
                      ui_class=str(qhist_col))
            col.on("click", lambda e=None, i=i: select_bin(i))
            bars.append(col)

        def marker_frac():
            if qmax <= qmin:
                return 100.0
            t = thr.value
            if log:
                f = (np.log10(t) - np.log10(qmin)) / (np.log10(qmax) - np.log10(qmin))
            else:
                f = (t - qmin) / (qmax - qmin)
            return float(min(1.0, max(0.0, f)) * 100.0)

        marker = Div(ui_style=computed(lambda: (
            f"position:absolute; top:0; bottom:0; left:{marker_frac():.1f}%; width:2px;"
            " background:var(--fg); opacity:0.65; pointer-events:none;"
        )))
        histo = Div(*bars, marker, ui_style=(
            "position:relative; display:flex; align-items:stretch; gap:1px;"
            " height:46px; margin:2px 0;"
        ))

        sw = Div(ui_class=on_cls(prop_switch, prop_switch_on, isolate))
        sw.on("click", lambda e=None: isolate.toggle())
        toggle_row = Div(
            Div("Isolate worst elements", ui_class=str(grow)),
            sw,
            ui_class="row items-center no-wrap " + str(gap_sm),
        )

        def readout():
            n = int(np.sum(q > thr.value))
            if isolate.value:
                return f"showing worst {n} of {total} · cond > {thr.value:.2f}"
            return f"worst {n} of {total} would isolate · cond > {thr.value:.2f}"

        return Div(
            stats, histo, toggle_row,
            Div(computed(readout), ui_class=str(mono) + " " + str(muted)),
            ui_class="column " + str(gap_sm),
        )

    # -- color change handlers (unchanged) --------------------------------
    def change_color(self, name, color):
        colors = []
        colmap = dict(zip(name, color))
        for fd in self.comp.mesh.ngmesh.FaceDescriptors():
            if fd.bcname in colmap:
                fd.color = colmap[fd.bcname]
            colors.append([int(fd.color[i] * 255) for i in range(4)])
        self.comp.elements2d.gpu_objects.colormap.set_colormap(colors)
        self.comp.elements2d.set_needs_update()
        self.comp.wgpu.scene.render()

    def change_edge_color(self, name, color):
        colmap = dict(zip(name, color))
        for n, c in colmap.items():
            self.ecolors[n] = [int(c[i] * 255) for i in range(4)]
        self.comp.edge_colors._value = self.ecolors
        edge_descriptors = list(self.comp.mesh.ngmesh.EdgeDescriptors())
        colors = [self.ecolors[ed.name] for ed in edge_descriptors]
        self.comp.elements1d._user_colors = colors
        self.comp.elements1d.set_needs_update()
        self.comp.wgpu.scene.render()

    def change_d_color(self, name, color):
        colmap = dict(zip(name, color))
        for d, c in colmap.items():
            self.dcolors[d] = [int(c[i] * 255) for i in range(4)]
        colors = [self.dcolors[d] for d in self.comp.mesh.GetMaterials()]
        if self.comp.elements3d is not None:
            self.comp.elements3d.colormap.set_colormap(colors)
            self.comp.elements3d.set_needs_update()
            self.comp.wgpu.scene.render()
