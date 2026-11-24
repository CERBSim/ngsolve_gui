"""Geometry views: the OCC geometry, its layer with hiding, click selection of
entities and meshing."""

import threading
from collections import defaultdict

import netgen.occ as ngocc
from ngapp.components import Observable, untracked
from ngsolve_webgpu.geometry import GeometryRenderer
from ngsolve_webgpu.pick import GeoPickResult

from ..core.part import Binding, Layer, Part

_NONE = 0xFFFFFFFF
KINDS = {2: "face", 1: "edge", 0: "vertex"}
LABELS = {"face": "Face", "edge": "Edge", "vertex": "Vertex", "solid": "Solid"}


def _key(p):
    return tuple(round(c, 8) for c in p)


class GeometryContext(Part):
    """The geometry and the adjacency of its entities (made on first use)."""

    key = "geometry_context"

    def __init__(self, geo):
        super().__init__()
        self.geo = geo
        self._adjacency = None

    def entity(self, kind, index):
        try:
            if kind == "face":
                return self.geo.faces[index]
            if kind == "edge":
                return self.geo.edges[index]
            if kind == "vertex":
                return list(self.geo.shape.vertices)[index]
            if kind == "solid":
                return list(self.geo.shape.solids)[index]
        except Exception:
            pass
        return None

    def describe(self, item):
        kind, index = item
        entity = self.entity(kind, index) if kind != "vertex" else None
        name = (getattr(entity, "name", None) or "") if entity is not None else ""
        return f"{LABELS.get(kind, kind)} {index}" + (f"  {name}" if name else "")

    def adjacency(self):
        """(face -> solids, edge -> faces, vertex -> faces), matched by centers."""
        if self._adjacency is not None:
            return self._adjacency
        geo = self.geo
        face_solids, edge_faces, vertex_faces = (defaultdict(set) for _ in range(3))
        try:
            centers = [_key(f.center) for f in geo.faces]
            for si, solid in enumerate(geo.shape.solids):
                own = {_key(f.center) for f in solid.faces}
                for fi, c in enumerate(centers):
                    if c in own:
                        face_solids[fi].add(si)
            edges = {_key(e.center): ei for ei, e in enumerate(geo.edges)}
            vertices = {_key(v.p): vi for vi, v in enumerate(set(geo.shape.vertices))}
            for fi, face in enumerate(geo.faces):
                for e in face.edges:
                    if _key(e.center) in edges:
                        edge_faces[edges[_key(e.center)]].add(fi)
                for v in face.vertices:
                    if _key(v.p) in vertices:
                        vertex_faces[vertices[_key(v.p)]].add(fi)
        except Exception:
            pass
        self._adjacency = (face_solids, edge_faces, vertex_faces)
        return self._adjacency


class GeometryLayer(Layer):
    """Faces, edges and vertices; hidden entities are drawn transparent.
    Edges and vertices of hidden faces only are hidden as well."""

    key = "geometry"
    order = 20
    requires = ("geometry_context", "selection")

    def __init__(self):
        super().__init__()
        self.show_faces = self.observable("show_faces", True)
        self.show_edges = self.observable("show_edges", True)
        self.show_vertices = self.observable("show_vertices", False)
        self.hidden = self.observable("hidden_entities", frozenset(), converter=frozenset)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("geometry_context")
        self.selection = view.part("selection")

    def build(self):
        return [GeometryRenderer(self.context.geo, clipping=self.view.clipping)]

    def pickables(self):
        return [(part, kind) for r in self.renderers.value
                for part, kind in ((r.faces, "face"), (r.edges, "edge"), (r.vertices, "vertex"))]

    def bindings(self):
        return [
            Binding("e", self.show_edges.toggle, "Toggle edges", mode="s"),
            Binding("v", self.show_vertices.toggle, "Toggle vertices", mode="s"),
            Binding("h", self.hide_selected, "Hide selected", mode="s"),
            Binding("u", self.show_all, "Unhide all", mode="s"),
        ]

    def hide_selected(self):
        items = self.selection.items.value
        if items:
            self.hidden.value = self.hidden.value | set(items)
            self.selection.items.value = ()
            self.selection.forget_hover()

    def show_all(self):
        self.hidden.value = frozenset()

    def alphas(self, n_faces, n_edges, n_vertices):
        """Alpha per face, edge and vertex for the hidden entities."""
        hidden = self.hidden.value
        explicit = defaultdict(set)
        for kind, index in hidden:
            explicit[kind].add(index)
        face_solids, edge_faces, vertex_faces = self.context.adjacency() if hidden else ({}, {}, {})
        solids = explicit["solid"]
        faces = {fi for fi in range(n_faces) if fi in explicit["face"]
                 or (face_solids.get(fi) and face_solids[fi] <= solids)}

        def of_faces(n, kind, adjacent):
            return [0.0 if i in explicit[kind] or (adjacent.get(i) and adjacent[i] <= faces)
                    else 1.0 for i in range(n)]
        return ([0.0 if i in faces else 1.0 for i in range(n_faces)],
                of_faces(n_edges, "edge", edge_faces),
                of_faces(n_vertices, "vertex", vertex_faces))

    def bind(self, r):
        def push_visible():
            hidden = any(p.suppresses("geometry_faces") for p in self.view.parts)
            r.faces.active = self.show_faces.value and not hidden
            r.edges.active = self.show_edges.value
            r.vertices.active = self.show_vertices.value or self.selection.pick_vertices.value
            for sub in (r.faces, r.edges, r.vertices):
                sub.set_needs_update()
            self.view.render()

        def push_alphas():
            self.hidden.value
            self._apply_alphas(r)
            self.view.render()

        def push_selection():
            by_kind = defaultdict(list)
            for kind, index in self.selection.items.value:
                by_kind[kind].append(index)
            r.faces.set_selection(by_kind["face"])
            r.edges.set_selection(by_kind["edge"])
            r.vertices.set_selection(by_kind["vertex"])
            self.view.render()

        def push_pick_modes():
            sel = self.selection
            r.faces._select_active = sel.pick_faces.value or sel.pick_solid.value
            r.edges._select_active = sel.pick_edges.value
            r.vertices._select_active = sel.pick_vertices.value
            scene = untracked(lambda: self.view.scene)
            if scene is not None and hasattr(scene, "_select_buffer_valid"):
                scene._select_buffer_valid = False
            self.view.render()

        for fn in (push_visible, push_alphas, push_selection, push_pick_modes):
            self.effect(fn)

    def wire(self, scene):
        # the colors of new renderers exist once the scene updated them
        if self.renderer is not None:
            self._apply_alphas(self.renderer)

    def _apply_alphas(self, r):
        subs = (r.faces, r.edges, r.vertices)
        if any(getattr(s, "colors", None) is None for s in subs):
            return
        alphas = untracked(lambda: self.alphas(*(len(s.colors) // 4 for s in subs)))
        for sub, alpha in zip(subs, alphas):
            colors = sub.colors
            colors[3::4] = alpha
            sub.set_colors(colors)


class Selection(Part):
    """Selected entities (click, Ctrl+click adds), the pick targets and the
    edits of name and local mesh size. Replaces the hover reaction of
    ``Picking`` (``hover``, ``out``, ``background``)."""

    key = "selection"
    requires = ("geometry_context",)

    def __init__(self):
        super().__init__()
        self.items = Observable((), "selection")
        self.pick_solid = Observable(False, "pick_solid")
        self.pick_faces = Observable(True, "pick_faces")
        self.pick_edges = Observable(True, "pick_edges")
        self.pick_vertices = Observable(False, "pick_vertices")
        self.maxh_error = Observable("", "maxh_error")
        self.name_error = Observable("", "name_error")
        self._click = None    # ctrl key of a click waiting for its pick
        self._last = None     # (event, kind) of the last hover pick
        self._exclusive = False
        self.pick_solid.on_change(lambda v, _o: self._exclude(v, ()))
        for obs in (self.pick_faces, self.pick_edges, self.pick_vertices):
            obs.on_change(lambda v, _o: self._exclude(v, (self.pick_solid,)))

    def _exclude(self, value, others):
        """Solids are picked alone."""
        if self._exclusive or not value:
            return
        self._exclusive = True
        try:
            for obs in others or (self.pick_faces, self.pick_edges, self.pick_vertices):
                obs.value = False
        finally:
            self._exclusive = False

    def attach(self, view):
        super().attach(view)
        self.context = view.part("geometry_context")

    def bindings(self):
        return [
            Binding("s", self.pick_solid.toggle, "Solids", mode="p"),
            Binding("f", self.pick_faces.toggle, "Faces", mode="p"),
            Binding("e", self.pick_edges.toggle, "Edges", mode="p"),
            Binding("v", self.pick_vertices.toggle, "Vertices", mode="p"),
        ]

    def wire(self, scene):
        self._click = None
        self._last = None

        def on_click(event):
            if event["button"] != 0:
                return
            self._click = event.get("ctrlKey", False)
            if self._last is not None:
                self.hover(*self._last)
            else:
                self.background(event)
        scene.input_handler.on_click(on_click)

    # -- edits -----------------------------------------------------------

    def entities(self):
        return [e for e in (self.context.entity(k, i) for k, i in self.items.value)
                if e is not None]

    def set_maxh(self, value):
        try:
            if value is None or value == "":
                value = None
            else:
                value = float(value)
                if value <= 0:
                    raise ValueError("Max mesh size must be positive.")
            self.maxh_error.value = ""
            for entity in self.entities():
                entity.maxh = value if value is not None else 1e99
        except ValueError as e:
            self.maxh_error.value = str(e)

    def set_name(self, value):
        try:
            for entity in self.entities():
                entity.name = value or None
            self.name_error.value = ""
        except ValueError as e:
            self.name_error.value = str(e)

    # -- picking -----------------------------------------------------------

    def _show_selection(self, picking):
        items = self.items.value
        if not items:
            picking.overlay.hide()
        elif len(items) > 1:
            picking.overlay.show_text(f"{len(items)} selected")
        else:
            picking.overlay.show_text(self.context.describe(items[0]))

    def hover(self, event, kind="face"):
        picking, layer = self.view.part("picking"), self.view.part("geometry")
        scene = self.view.scene
        try:
            self._last = (event, kind)
            if self._click is None and not picking.enabled.value:
                return
            result = GeoPickResult(event, self.context.geo, scene.options)
            pos = result.world_pos
            coords = f"({pos[0]:>9.4f}, {pos[1]:>9.4f}, {pos[2]:>9.4f})"
            solid = self.pick_solid.value and result.geo_type == 2
            if solid:
                index = int(layer.renderer.faces._solid_ids[result.index])
                name = getattr(self.context.entity("solid", index), "name", "") or ""
                text = f"{'Solid':<8s}{index:<6d} {name:<12s} {coords}"
                item = ("solid", index)
            else:
                text = f"{result.kind_label:<8s}{result.index:<6d} {result.name or '':<12s} {coords}"
                item = (KINDS.get(result.geo_type, "face"), result.index)
            if item in layer.hidden.value:
                self._click = None
                self.forget_hover()
                return
            for hl in picking.highlights:
                hl.renderer_id = event.obj_id
                hl.element_id = _NONE
                hl.region_index = _NONE if solid else result.index
                hl.solid_index = item[1] if solid else _NONE
                hl.update_buffer()
            picking.overlay.show_text(text)
            if self._click is not None:
                ctrl, self._click = self._click, None
                items = list(self.items.value)
                if not ctrl:
                    items = [item]
                elif item in items:
                    items.remove(item)
                else:
                    items.append(item)
                self.items.value = tuple(items)
            scene._render_highlight()
        except Exception:
            picking.overlay.hide()

    def forget_hover(self):
        """Drop the hover highlight and card (the entity went away)."""
        picking = self.view.part("picking")
        self._last = None
        picking.clear_highlight()
        self._show_selection(picking)
        if self.view.scene is not None:
            self.view.scene._render_highlight()

    def out(self, ev):
        picking = self.view.part("picking")
        self._last = None
        picking.clear_highlight()
        self._show_selection(picking)
        self.view.render()

    def background(self, ev):
        picking = self.view.part("picking")
        self._last = None
        picking.clear_highlight()
        if self._click is not None:
            self._click = None
            self.items.value = ()
        self._show_selection(picking)
        self.view.scene._render_highlight()


class Meshing(Part):
    """Meshing parameters; ``generate`` meshes in a thread."""

    key = "meshing"
    requires = ("geometry_context",)

    def __init__(self):
        super().__init__()
        self.maxh = self.observable("maxh", 1000, converter=float)
        self.segments_per_edge = self.observable("segments_per_edge", 0.2, converter=float)
        self.curvaturesafety = self.observable("curvaturesafety", 1.5, converter=float)
        self.closeedgefac = self.observable("closeedgefac", None)

    def attach(self, view):
        super().attach(view)
        self.context = view.part("geometry_context")

    def options(self):
        return {"maxh": self.maxh.value, "segmentsperedge": self.segments_per_edge.value,
                "curvaturesafety": self.curvaturesafety.value,
                "closeedgefac": self.closeedgefac.value}

    def generate(self, on_mesh, on_error, on_done=None):
        """Mesh a copy of the geometry in a thread; ``on_mesh(mesh)`` with the
        ngsolve mesh, ``on_error(message)``; an abort calls neither. Returns
        the thread and an event set when meshing ended."""
        import netgen.meshing as ngm
        import ngsolve as ngs
        from .preview import get_terminate, set_terminate

        geo = ngocc.OCCGeometry(self.context.geo.shape)
        options = self.options()
        done = threading.Event()

        def work():
            error = None
            ng_mesh = ngm.Mesh()
            try:
                set_terminate(False)
                with ngs.TaskManager():
                    geo.GenerateMesh(mesh=ng_mesh, **options)
            except Exception as e:
                error = e
            finally:
                done.set()
            aborted = get_terminate()
            set_terminate(False)
            try:
                if error is not None:
                    msg = str(error)
                    if not (aborted or "stop" in msg.lower()):
                        on_error(msg)
                elif not aborted:
                    on_mesh(ngs.Mesh(ng_mesh))
            finally:
                if on_done is not None:
                    on_done()

        thread = threading.Thread(target=work, name="Meshing", daemon=True)
        thread.start()
        return thread, done

