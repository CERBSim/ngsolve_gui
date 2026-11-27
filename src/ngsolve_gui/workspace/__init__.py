"""Workspace: the objects in the namespaces of the loaded scripts, described
by inspectors (one per backend, see ``ngsolve.py``)."""

import os
import re
import types
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
    meshes and regions of their mesh (any if None). ``ident`` is the id of
    the object. A python object (``container``) with such members has their
    names as ``members`` (``solver.a``, ``solver.gfus[0]``), they have it as
    ``parent``. ``parts`` are ``(suffix, step)`` of objects that are part of
    this one (the components of a grid function): they become its members
    and count as this object."""

    name: str
    kind: str
    icon: str
    details: tuple = ()
    regions: tuple = ()
    drawable: bool = False
    on_mesh: bool = False
    mesh_id: int | None = None
    target: bool = False
    ident: int = 0
    members: tuple = ()
    parent: str | None = None
    parts: tuple = ()
    container: bool = False


_inspectors = []
_memory = []


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


def register_memory(fn):
    """``fn(obj) -> (ram, vram) | None`` in bytes, either None if unknown;
    later registrations are asked first."""
    _memory.insert(0, fn)
    return fn


def memory(obj):
    for fn in _memory:
        try:
            mem = fn(obj)
        except Exception:
            mem = None
        if mem is not None:
            return mem
    return None, None


def process_ram():
    try:
        import psutil

        return psutil.Process().memory_info().rss
    except ImportError:
        pass
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return None


def gpu_total():
    try:
        from webgpu.utils import gpu_total
    except ImportError:
        return None
    return gpu_total()


def format_bytes(n):
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" or n >= 100 else f"{n:.1f} {unit}"
        n /= 1000


_MAX_DEPTH = 3      # levels of python objects looked into
_MAX_ITEMS = 20     # items of a list or dict member
_LIBRARIES = ("builtins", "ngsolve", "netgen", "pyngcore", "numpy", "ngsolve_gui", "ngapp")


def _plain(obj):
    """A python object whose attributes may hold workspace objects."""
    if isinstance(obj, (type, types.ModuleType, types.FunctionType, types.MethodType)):
        return False
    return hasattr(obj, "__dict__") and \
        (type(obj).__module__ or "").split(".")[0] not in _LIBRARIES


def _members(obj):
    """``(suffix, step, value)`` of the attributes and their list and dict items."""
    for key, value in list(vars(obj).items()):
        if key.startswith("_"):
            continue
        if isinstance(value, (list, tuple)):
            for i, v in enumerate(value[:_MAX_ITEMS]):
                yield f".{key}[{i}]", (key, i), v
        elif isinstance(value, dict):
            for k, v in list(value.items())[:_MAX_ITEMS]:
                if isinstance(k, (str, int)):
                    yield f".{key}[{k!r}]", (key, k), v
        else:
            yield f".{key}", (key,), value


class Workspace:
    """Scripts run in threads and change their namespace; ``refresh`` (after
    a script, on Draw, by the user) rescans a copy of it while ``shown``,
    else on the next show."""

    def __init__(self):
        self._own = {}
        self._namespaces = [self._own]
        self._stale = False
        self._paths = {}     # entry name -> (name in a namespace, steps)
        self._by_name = {}
        self._part_of = {}   # id of a part -> name of the object it is part of
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
        root, steps = self._paths.get(name, (name, ()))
        obj = self._objects().get(root)
        try:
            for step in steps:
                obj = _step(obj, step)
        except (AttributeError, LookupError, TypeError):
            return None
        return obj

    def part_of(self, name):
        """Name of the object the object ``name`` is part of, or None."""
        obj = self.get(name)
        return None if obj is None else self._part_of.get(id(obj))

    def _leaves(self, name, out):
        """The objects (not python objects) of an entry and its members by
        id; a part counts as the object it is part of."""
        e = self._by_name.get(name)
        if e is None:
            return out
        if e.container:
            for m in e.members:
                self._leaves(m, out)
            return out
        obj, seen = self.get(name), set()
        while obj is not None and id(obj) in self._part_of and id(obj) not in seen:
            seen.add(id(obj))
            obj = self.get(self._part_of[id(obj)])
        if obj is not None:
            out.setdefault(id(obj), obj)
        return out

    def _memory(self, objs):
        ram = vram = None
        for obj in objs:
            r, v = memory(obj)
            if r is not None:
                ram = (ram or 0) + r
            if v is not None:
                vram = (vram or 0) + v
        return ram, vram

    def memory(self, name):
        """``(ram, vram)`` in bytes, None where unknown; of a python object
        the sum of its members, each counted once."""
        return self._memory(self._leaves(name, {}).values())

    def memory_report(self):
        """Process RAM, GPU buffer bytes and ``(name, kind, ram, vram)`` of
        the top level entries. Each object counts once: under its own name,
        else in the first python object holding it; a part counts as its
        whole, and only if nothing else holds that."""
        tops = [e for e in self.entries.value if e.parent is None]
        done, rows = set(), []
        for e in sorted(tops, key=lambda e: (e.ident in self._part_of, e.container)):
            objs = [o for i, o in self._leaves(e.name, {}).items() if i not in done]
            done.update(id(o) for o in objs)
            ram, vram = self._memory(objs)
            if ram or vram:
                rows.append((e.name, e.kind, ram or 0, vram or 0))
        return process_ram(), gpu_total(), rows

    def _scan(self, name, obj, path, parent, depth, holders, out):
        """Entries of obj and, for a python object, of its members;
        ``holders`` are the python objects above (cycles)."""
        entry = inspect(name, obj)
        if entry is None:
            if depth >= _MAX_DEPTH or id(obj) in holders or not _plain(obj):
                return None
            holders = holders | {id(obj)}
            sub = []
            members = tuple(child.name for suffix, step, value in _members(obj)
                            if (child := self._scan(name + suffix, value, (path[0], path[1] + (step,)),
                                                    name, depth + 1, holders, sub)))
            if not members:
                return None
            entry = Entry(name, type(obj).__name__, "mdi-package-variant-closed", members=members,
                          container=True)
        else:
            sub, members = [], []
            for suffix, step in entry.parts:
                try:
                    part = _step(obj, step)
                except (AttributeError, LookupError, TypeError):
                    continue
                self._part_of.setdefault(id(part), name)
                child = self._scan(name + suffix, part, (path[0], path[1] + (step,)),
                                   name, depth + 1, holders, sub)
                if child is not None:
                    members.append(child.name)
            entry = replace(entry, members=tuple(members))
        out.append(replace(entry, ident=id(obj), parent=parent))
        out.extend(sub)
        self._paths[name] = path
        return entry

    def refresh(self):
        self._stale = not self.shown.value
        if self._stale:
            return
        objs = self._objects()
        self._paths, self._part_of, entries = {}, {}, []
        for name, obj in objs.items():
            self._scan(name, obj, (name, ()), None, 0, frozenset(), entries)
        names = {}
        for e in sorted(entries, key=lambda e: e.parent is not None):
            names.setdefault(e.ident, e.name)
        # a part stored elsewhere links to the object it is part of
        entries = [replace(e, details=(("part of", "", id(self.get(whole))),) + e.details)
                   if (whole := self._part_of.get(e.ident)) and e.parent != whole else e
                   for e in entries]
        entries = tuple(replace(e, details=tuple(_resolve(d, names) for d in e.details))
                        for e in entries)
        self._by_name = {e.name: e for e in entries}
        self.entries.value = entries


def _step(obj, step):
    obj = getattr(obj, step[0])
    return obj[step[1]] if len(step) > 1 else obj


def _resolve(detail, names):
    label, value, *ref = detail
    name = names.get(ref[0]) if ref else None
    return (label, value if name is None else name, name)
