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


@standalone_app_test
def test_mesh_view_rebuilds_once_and_keeps_regions():
    from netgen.occ import Box, Glue, OCCGeometry, Pnt
    from ngsolve import Mesh

    from ngsolve_gui.app_data import AppData
    from ngsolve_gui.mesh import MeshComponent

    left, right = Box(Pnt(0, 0, 0), Pnt(1, 1, 1)), Box(Pnt(1, 0, 0), Pnt(2, 1, 1))
    left.mat("left")
    right.mat("right")
    mesh = Mesh(OCCGeometry(Glue([left, right])).GenerateMesh(maxh=0.5))
    app_data = AppData()
    tab = app_data.add_tab("m", MeshComponent, {"obj": mesh}, app_data)
    mount(tab)
    view = tab.view
    view.part("regions").set_region_visible("left", False)
    draws = view.draws
    view.part("elements3d").visible.value = True
    assert view.draws == draws + 1
    drawn = [r for r in view.scene_objects.value if hasattr(r, "region_visibility")]
    assert drawn and all(r.region_visibility is view.part("regions").visibility for r in drawn)

    # element filters use the bits of the visibility buffer, not own buffers
    el3d = view.part("elements3d")
    renderer = el3d.renderer
    tab.set_quality_threshold(0.0)
    assert view.part("regions").visibility.element_counts == (0, mesh.ne)
    assert el3d.renderer is not renderer and el3d.renderer.data is view.part("mesh").base_data
    renderer, draws = el3d.renderer, view.draws
    tab.set_quality_threshold(1e9)
    assert el3d.renderer is renderer and view.draws == draws


@standalone_app_test
def test_function_retarget_changes_bindings_without_remount():
    from ngsolve import CF, Mesh, unit_square, x, y

    from ngsolve_gui.app_data import AppData
    from ngsolve_gui.function import FunctionComponent

    mesh = Mesh(unit_square.GenerateMesh(maxh=0.3))
    app_data = AppData()
    tab = app_data.add_tab("f", FunctionComponent, {"obj": x, "mesh": mesh}, app_data)
    fe = mount(tab)
    view, surface = tab.view, tab.view.part("surface").renderer

    def modes():
        return {t for t, _, _ in tab.get_keybindings()["modes"]}

    assert "d" in modes() and "x" not in modes()
    draws = view.draws
    tab.set_cf(CF((x, 1j * y)))
    assert view.draws == draws + 1 and view._index in fe.mounted
    assert "x" in modes() and "d" not in modes()
    assert view.part("surface").renderer is not surface


def _changed(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value * 2 + 0.5
    return value


@standalone_app_test
def test_state_round_trip_per_preset():
    from netgen.occ import Box, OCCGeometry, Pnt
    from ngsolve import CF, Mesh, x, y, z

    from ngsolve_gui.app_data import AppData
    from ngsolve_gui.function import FunctionComponent
    from ngsolve_gui.geometry import GeometryComponent
    from ngsolve_gui.mesh import MeshComponent

    geo = OCCGeometry(Box(Pnt(0, 0, 0), Pnt(1, 1, 1)))
    mesh = Mesh(geo.GenerateMesh(maxh=0.5))
    for cls, data in ((MeshComponent, {"obj": mesh}),
                      (FunctionComponent, {"obj": CF((x, y, z)), "mesh": mesh}),
                      (GeometryComponent, {"obj": geo})):
        app_data = AppData()
        tab = app_data.add_tab("t", cls, data, app_data)
        mount(tab)
        state = tab.view.state()
        tab.view.load_state({k: _changed(v) for k, v in state.items()})
        saved = tab.saved_state()
        changed = {k for k in state if saved[k] != state[k]}
        assert len(changed) > len(state) // 2, cls

        app_data = AppData()
        app_data._settings = saved
        restored = app_data.add_tab("t", cls, data, app_data)
        mount(restored)
        assert restored.saved_state() == saved, cls
