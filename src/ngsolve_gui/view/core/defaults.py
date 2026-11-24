"""Defaults of a viewport (axes shown, picking on, ...) that outlive it."""

from ngapp.components import Observable


class Defaults:
    """In-memory defaults; an app passes its own (e.g. over user settings)
    with the same ``ref``."""

    def __init__(self, values=None):
        self._refs = {}
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self.ref(key, default).value

    def ref(self, key, default=None, converter=None):
        obs = self._refs.get(key)
        if obs is None:
            obs = self._refs[key] = Observable(
                self._values.get(key, default), key, converter=converter)
        return obs


class SettingsDefaults(Defaults):
    """Defaults stored in an ngapp settings file."""

    def __init__(self, settings):
        super().__init__()
        self._settings = settings

    def ref(self, key, default=None, converter=None):
        return self._settings.ref(key, default, converter)
