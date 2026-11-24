"""Workspace: the objects in the namespaces of the loaded scripts, described
by inspectors (one per backend, see ``ngsolve.py``)."""

import re
from dataclasses import dataclass, replace

from ngapp.components import Observable


@dataclass(frozen=True)
class Entry:
    """``details`` are ``(label, value)`` or ``(label, value, ref)`` with
    ``ref`` the id of another object; the scan turns them into ``(label,
    value, name)``, the value the name of that object if it is in the
    workspace. ``regions`` are ``(kind, indices, name)``, kind "material" or
    "boundary". ``mesh_id`` identifies the mesh of a mesh, region or grid
    function; functions with ``on_mesh`` can be drawn on the ``target``
    meshes and regions of their mesh (any if None)."""

    name: str
    kind: str
    icon: str
    details: tuple = ()
    regions: tuple = ()
    drawable: bool = False
    on_mesh: bool = False
    mesh_id: int | None = None
    target: bool = False


_inspectors = []


def identifier(text):
    """A python name made from ``text`` (a file stem, a tab title)."""
    name = re.sub(r"\W", "_", text)
    return "n" + name if not name or not name[0].isalpha() else name


def register_inspector(fn):
    """``fn(name, obj) -> Entry | None``; later registrations are asked first."""
    _inspectors.insert(0, fn)
    return fn


def inspect(name, obj):
    for fn in _inspectors:
        try:
            entry = fn(name, obj)
        except Exception:
            entry = None
        if entry is not None:
            return entry
    return None


class Workspace:
    """Scripts run in threads and change their namespace; ``refresh`` (after
    a script, on Draw, by the user) rescans a copy of it while ``shown``,
    else on the next show."""

    def __init__(self):
        self._own = {}
        self._namespaces = [self._own]
        self._stale = False
        self.entries = Observable((), "workspace_entries")
        self.shown = Observable(False, "workspace_shown")
        self.shown.on_change(lambda v, _o: v and self._stale and self.refresh())

    def add_namespace(self, ns):
        self._namespaces.append(ns)
        self.refresh()

    def _objects(self):
        objs = {}
        for ns in self._namespaces:
            objs.update((k, v) for k, v in dict(ns).items() if not k.startswith("_"))
        return objs

    def add(self, name, obj):
        """An object made in the GUI (a generated mesh)."""
        self._own[name] = obj
        self.refresh()

    def get(self, name):
        return self._objects().get(name)

    def refresh(self):
        self._stale = not self.shown.value
        if self._stale:
            return
        objs = self._objects()
        names = {}
        for name, obj in objs.items():
            names.setdefault(id(obj), name)
        entries = (inspect(name, obj) for name, obj in objs.items())
        self.entries.value = tuple(replace(e, details=tuple(_resolve(d, names) for d in e.details))
                                   for e in entries if e is not None)


def _resolve(detail, names):
    label, value, *ref = detail
    name = names.get(ref[0]) if ref else None
    return (label, value if name is None else name, name)
