"""Key maps: bindings of the parts merged into the format of
ngapp.keybindings (``{"flat": [...], "modes": [...]}``)."""

MODE_TITLES = {
    "s": "Show", "c": "Clipping", "d": "Deformation", "m": "Colormap",
    "x": "Complex", "g": "Regions", "n": "Numbers", "v": "View", "p": "Pick",
}


def merge(bindings, extra=None):
    """Bindings and a legacy spec in one spec; modes of the same trigger are
    merged. Raises on a key bound twice in one mode."""
    flat, modes, names = [], {}, {}

    def add_flat(key, action, desc, group):
        if any(f[0] == key for f in flat):
            raise ValueError(f"key {key!r} bound twice")
        flat.append((key, action, desc, group))

    def add_mode(trigger, name, key, action, desc):
        entries = modes.setdefault(trigger, [])
        names.setdefault(trigger, name)
        if any(e[0] == key for e in entries):
            raise ValueError(f"key {key!r} bound twice in mode {name!r}")
        entries.append((key, action, desc))

    for b in bindings:
        if b.mode is None:
            add_flat(b.key, b.action, b.desc, b.group)
        else:
            add_mode(b.mode, MODE_TITLES.get(b.mode, b.mode), b.key, b.action, b.desc)
    for key, action, desc, group in (extra or {}).get("flat", []):
        add_flat(key, action, desc, group)
    for trigger, name, entries in (extra or {}).get("modes", []):
        for key, action, desc in entries:
            add_mode(trigger, name, key, action, desc)
    return {"flat": flat, "modes": [(t, names[t], e) for t, e in modes.items()]}
