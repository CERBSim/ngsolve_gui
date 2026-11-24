"""Backends say which kind of view shows an object; Draw and the object
explorer dispatch through them instead of a type table."""

_backends = []


def register_backend(name, target):
    """``target(obj)`` returns ``(kind, obj)``, the kind of view (``"mesh"``,
    ``"function"``, ...) and the object in the form those views take, or
    None. Later registrations are asked first; a name registered again
    replaces the old entry."""
    _backends[:] = [b for b in _backends if b[0] != name]
    _backends.insert(0, (name, target))


def view_target(obj):
    for _name, target in _backends:
        found = target(obj)
        if found is not None:
            return found
    return None
