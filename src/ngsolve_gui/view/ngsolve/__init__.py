"""ngsolve backend of the view: parts that call ngsolve or netgen."""

from ..core.backends import register_backend
from .backend import target

register_backend("ngsolve", target)
