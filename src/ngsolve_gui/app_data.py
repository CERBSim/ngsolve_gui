import itertools
import threading
import weakref

from ngsolve_webgpu import *
from webgpu.camera import Camera
from ngapp.components import Observable, batch, computed

_uids = itertools.count(1)


class AppData:
    """Workspace (tabs, active tab) and the services shared by all tabs: GPU
    cache, shared cameras, global clipping.

    ``tabs`` holds the records (name, title, type, icon, uid); a tab drawn
    again under its name gets a new uid. ``shown`` follows ``active``, after
    a short delay for Draw calls, so a burst of them mounts only the last tab.
    """

    def __init__(self):
        self.tabs = Observable((), "tabs")
        self.active = Observable(None, "active_tab")
        self.shown = Observable(None, "shown_tab")
        self.current = computed(lambda: self._record(self.shown.value), "current_tab")
        self._components = {}   # uid -> component
        self._saved = {}        # uid -> saved data of a loaded tab, built when shown
        self._settings = {}     # settings of the tab under construction
        self._building = None   # record of a drawn tab under construction
        self._timer = None
        self._timer_lock = threading.Lock()
        self._gpu_cache = {}
        self._clipping = Clipping()
        self._cameras = {}

    @property
    def clipping(self):
        return self._clipping

    # -- workspace --------------------------------------------------------

    def _record(self, name):
        b = self._building
        if b is not None and b["name"] == name:
            return b
        for t in self.tabs.value:
            if t["name"] == name:
                return t
        return None

    def get_tab(self, name):
        return self._record(name)

    def component(self, uid):
        """The component of a tab, built on first use for loaded tabs."""
        comp = self._components.get(uid)
        if comp is None:
            rec = next((t for t in self.tabs.value if t["uid"] == uid), None)
            if rec is None:
                return None
            from .registry import get_component_info

            cls = get_component_info(rec["type"])["cls"]
            saved = self._saved.pop(uid, {})
            self._settings = saved.get("settings", {})
            try:
                comp = cls(rec["name"], saved.get("data", {}), app_data=self)
            finally:
                self._settings = {}
            self._components[uid] = comp
        return comp

    def saved_settings(self):
        """Settings saved for the tab being built (empty for a new tab)."""
        return self._settings

    @property
    def active_component(self):
        rec = self.current.value
        return self.component(rec["uid"]) if rec is not None else None

    def select(self, name):
        self._cancel_timer()
        with batch():
            self.active.value = name
            self.shown.value = name

    def add_tab(self, title: str, cls: type, *args, **kwargs):
        from .registry import get_registry

        name = title.lower().replace(" ", "_")
        type_key, icon = "unknown", "mdi-vector-triangle"
        for key, info in get_registry().items():
            if info["cls"] is cls:
                type_key, icon = key, info["icon"]
                break
        rec = {"name": name, "title": title, "type": type_key, "icon": icon,
               "uid": next(_uids)}
        self._building = rec
        try:
            component = cls(name, *args, **kwargs)
        finally:
            self._building = None
        self._components[rec["uid"]] = component
        tabs = [t for t in self.tabs.value if t["name"] != name] + [rec]
        self._drop_unused(tabs)
        with batch():
            self.tabs.value = tuple(tabs)
            self.active.value = name
        self._schedule_shown()
        return component

    def delete_tab(self, name):
        tabs = [t for t in self.tabs.value if t["name"] != name]
        self._drop_unused(tabs)
        active = self.active.value
        if active == name or self._record(active) is None:
            active = tabs[0]["name"] if tabs else None
        with batch():
            self.tabs.value = tuple(tabs)
            self.select(active)

    def rename_tab(self, name, title):
        self.tabs.value = tuple(
            dict(t, title=title) if t["name"] == name else t for t in self.tabs.value)

    def _drop_unused(self, tabs):
        uids = {t["uid"] for t in tabs}
        for uid in [u for u in self._components if u not in uids]:
            del self._components[uid]

    def _schedule_shown(self, delay=0.1):
        self._cancel_timer()
        with self._timer_lock:
            self._timer = threading.Timer(delay, self._show_active)
            self._timer.daemon = True
            self._timer.start()

    def _cancel_timer(self):
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _show_active(self):
        with self._timer_lock:
            self._timer = None
        self.shown.value = self.active.value

    # -- persistence ------------------------------------------------------

    def get_save_data(self):
        from ngapp.observable import snapshot

        tabs = []
        for rec in self.tabs.value:
            comp = self._components.get(rec["uid"])
            if comp is not None:
                saved = {"data": comp.data, "settings": snapshot(comp)}
            else:
                saved = self._saved.get(rec["uid"], {})
            tabs.append((rec, saved))
        return {"tabs": tabs, "active": self.active.value}

    def load_save_data(self, data):
        recs = []
        self._components.clear()
        self._saved.clear()
        for rec, saved in data["tabs"]:
            rec = dict(rec, uid=next(_uids))
            self._saved[rec["uid"]] = saved
            recs.append(rec)
        with batch():
            self.tabs.value = tuple(recs)
            self.select(data.get("active"))

    # -- shared services --------------------------------------------------

    def get_shared_camera(self, group):
        """Camera shared by all views of the same mesh/geometry.

        *group* is the object identifying the sharing group (a geometry, or a
        mesh without one); ``None`` means "no sharing". Returns
        ``(camera, is_new)`` - with *is_new* True the caller owns the initial
        fit, otherwise it adopts the view the group already has.
        """
        if group is None:
            return Camera(), True
        key = id(group)
        entry = self._cameras.get(key)
        if entry is not None:
            return entry[1], False
        camera = Camera()
        try:
            ref = weakref.ref(group, lambda _r, k=key: self._cameras.pop(k, None))
        except TypeError:
            ref = group          # not weak-referenceable: hold it instead
        self._cameras[key] = [ref, camera]
        return camera, True

    def get_mesh_gpu_data(self, mesh):
        key = repr(mesh)
        if key not in self._gpu_cache:
            self._gpu_cache[key] = MeshData(mesh)
        return self._gpu_cache[key]

    def get_function_gpu_data(self, cf, mesh, **kwargs):
        key = hash((repr(cf), repr(mesh), tuple(sorted(kwargs.items()))))
        if key not in self._gpu_cache:
            mdata = self.get_mesh_gpu_data(mesh)
            self._gpu_cache[key] = FunctionData(mdata, cf, **kwargs)
        return self._gpu_cache[key]

    def set_needs_redraw(self):
        for comp in list(self._components.values()):
            scene = getattr(comp, "scene", None)  # PlotComponent has no scene
            if scene is None:
                continue
            for obj in getattr(scene, "render_objects", []):
                obj.set_needs_update()
