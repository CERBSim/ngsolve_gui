"""View core without a browser."""

import ast
import subprocess
import sys
from pathlib import Path

from ngapp.test_utils import mount, standalone_app_test

import ngsolve_gui.view.core as core
from ngsolve_gui.view.core import Raw, Viewport
from ngsolve_gui.view.core.tools.clipping import ClippingTools


class _Renderer:
    active = True

    def get_bounding_box(self):
        return ((0, 0, 0), (1, 1, 1))


@standalone_app_test
def test_new_scene_gets_the_input_handlers():
    # each draw creates a new scene with its own input handler
    view = Viewport()
    raw = Raw()
    view.add(raw, ClippingTools())
    mount(view)
    raw.set([_Renderer()])
    first = view.scene
    raw.set([_Renderer()])
    assert view.scene is not first
    assert {"dblclick", "drag", "wheel"} <= set(view.scene.input_handler._callbacks)


def test_core_imports_no_ngsolve_and_no_app():
    for path in Path(core.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in ("ngsolve", "netgen"), (path, name)
    code = ("import sys, ngsolve_gui.view.core\n"
            "bad = [m for m in ('ngsolve_gui.app', 'ngsolve_gui.app_data',"
            " 'ngsolve_gui.file_loader') if m in sys.modules]\n"
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], check=True)
