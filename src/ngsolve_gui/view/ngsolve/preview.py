"""Live preview of the surface mesh while a geometry is meshed."""

import threading
import time

from ngapp.components import Observable, untracked
from ngsolve_webgpu.mesh import MeshData, MeshElements2d, MeshWireframe2d

from ..core.part import Layer


def set_terminate(flag: bool):
    """Set netgen's global meshing terminate flag, if the binding is available.

    The binding (`_SetTerminate`) requires a netgen build that exposes it; until
    then this is a no-op and abort falls back to the footer's thread interrupt.
    """
    try:
        from netgen.libngpy._meshing import _SetTerminate

        _SetTerminate(bool(flag))
    except Exception:
        pass


def get_terminate() -> bool:
    """Whether a meshing abort has been requested (False if binding absent)."""
    try:
        from netgen.libngpy._meshing import _GetTerminate

        return bool(_GetTerminate())
    except Exception:
        return False


class MeshingPreview(Layer):
    """The growing surface mesh over the geometry edges (its faces are hidden
    while a mesh is shown). ``start(mesh)``, ``refresh()``, ``end()``."""

    key = "meshing_preview"
    order = 30

    def __init__(self):
        super().__init__()
        self.mesh = Observable(None, "preview_mesh")
        self._data = None

    def build(self):
        mesh = self.mesh.value
        if mesh is None:
            return []
        clipping = self.view.clipping
        with untracked():
            self._data = MeshData(mesh)
            self._data.subdivision = 1
            return [MeshElements2d(self._data, clipping=clipping),
                    MeshWireframe2d(self._data, clipping=clipping)]

    def suppresses(self, key):
        return key == "geometry_faces" and self.mesh.value is not None

    def start(self, mesh):
        self.mesh.value = mesh

    def refresh(self):
        if self._data is None:
            return
        self._data.set_needs_update()
        for r in self.renderers.value:
            r.set_needs_update()
        self.view.render()

    def end(self):
        self.mesh.value = None
        self._data = None


class PreviewPoller:
    """Polls a netgen mesh being generated and shows it in a preview layer
    once it has surface elements; holds updates while the camera moves and
    stops updating when the volume meshing starts."""

    interval = 0.15
    quiet = 0.2

    def __init__(self, layer, last_interaction=lambda: 0.0):
        self.layer = layer
        self.last_interaction = last_interaction
        self.mesh = None
        self._stop = threading.Event()
        self._thread = None
        self._shown = False

    def bind(self, mesh):
        self.mesh = mesh
        self._thread = threading.Thread(target=self._poll, name="MeshPreview", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._shown:
            self.layer.end()

    def _poll(self):
        try:
            from netgen.libngpy._meshing import _GetStatus
        except Exception:
            _GetStatus = None
        last, frozen = None, False
        while not self._stop.is_set():
            try:
                n2d = len(self.mesh.Elements2D())
                nfd = len(self.mesh.FaceDescriptors())
                ts = self.mesh._timestamp
            except Exception:
                n2d, nfd, ts = 0, 0, None
            try:
                if not self._shown and n2d > 0 and nfd > 0:
                    self.layer.start(self.mesh)
                    self._shown, last = True, ts
                elif self._shown and not frozen:
                    status = ""
                    if _GetStatus is not None:
                        try:
                            status = _GetStatus()[0] or ""
                        except Exception:
                            pass
                    if "volume" in status.lower():
                        frozen = True
                        self.layer.refresh()
                    elif ts != last and time.monotonic() - self.last_interaction() >= self.quiet:
                        last = ts
                        self.layer.refresh()
            except Exception as e:
                print("mesh preview:", e)
                return
            self._stop.wait(self.interval)
