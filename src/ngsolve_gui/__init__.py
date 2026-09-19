try:
    from ._version import version as __version__
except (ImportError, ModuleNotFoundError):
    __version__ = "0.0.0.dev0"


def __getattr__(name):
    if name == "NGSolveGui":
        from .app import NGSolveGui

        return NGSolveGui
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
