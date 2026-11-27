"""Workspace scan and region highlight from the explorer."""

from ngapp.test_utils import mount, standalone_app_test


@standalone_app_test
def test_workspace_lists_objects_and_highlights_regions():
    from netgen.occ import Box, Glue, OCCGeometry, Pnt, X
    import ngsolve as ngs

    from ngsolve_gui.app_data import AppData
    from ngsolve_gui.mesh import MeshComponent
    from ngsolve_gui.workspace import Workspace
    from ngsolve_gui.workspace.ngsolve import region_marks

    left, right = Box(Pnt(0, 0, 0), Pnt(1, 1, 1)), Box(Pnt(1, 0, 0), Pnt(2, 1, 1))
    left.mat("left")
    right.mat("right")
    left.faces.Min(X).name = "inlet"
    mesh = ngs.Mesh(OCCGeometry(Glue([left, right])).GenerateMesh(maxh=0.5))
    fes = ngs.H1(mesh, order=2)
    u, v = fes.TnT()
    ns = {"mesh": mesh, "fes": fes, "gf": ngs.GridFunction(fes),
          "a": ngs.BilinearForm(u * v * ngs.dx), "x": ngs.x, "_m": mesh, "n": 3}
    ws = Workspace()
    ws.add_namespace(ns)
    assert ws.entries.value == ()   # folded: no scan
    ws.shown.value = True
    assert [(e.name, e.kind) for e in ws.entries.value] == [
        ("mesh", "Mesh"), ("fes", "Space"), ("gf", "GridFunction"), ("a", "BilinearForm")]
    # references show as the python names
    assert ("space", "fes", "fes") in ws.entries.value[2].details
    # a name covers all its indices
    regions = ws.entries.value[0].regions
    assert ("material", (1,), "right") in regions
    assert ("boundary", tuple(range(1, 11)), "default") in regions
    # memory: the unassembled form has none
    _, _, rows = ws.memory_report()
    assert [r[0] for r in rows] == ["mesh", "fes", "gf"] and all(r[2] > 0 for r in rows)

    app_data = AppData()
    tab = app_data.add_tab("m", MeshComponent, {"obj": mesh}, app_data)
    mount(tab)
    picking = tab.view.part("picking")
    flags = tab.view.part("elements2d").renderer.region_selection.flags
    # a material without drawn volumes shows as its boundary faces
    picking.mark_regions(region_marks(mesh, "material", (0,)))
    left_faces = [i for i, fd in enumerate(mesh.ngmesh.FaceDescriptors()) if 1 in (fd.domin, fd.domout)]
    assert list(flags.nonzero()[0]) == left_faces
    picking.mark_regions({})
    assert not flags.any()

    # boundaries of a 2D mesh show as thick lines
    mesh2 = ngs.Mesh(ngs.unit_square.GenerateMesh(maxh=0.3))
    tab = app_data.add_tab("m2", MeshComponent, {"obj": mesh2}, app_data)
    mount(tab)
    tab.view.part("picking").mark_regions(region_marks(mesh2, "boundary", (1,)))
    assert [c[3] for c in tab.view.part("boundary_marks").renderer._user_colors] == [0, 0.6, 0, 0]


def test_python_objects_list_their_members():
    import ngsolve as ngs

    import ngsolve_gui.workspace.ngsolve  # noqa: F401
    from ngsolve_gui.workspace import Workspace

    class Solver:
        def __init__(self, mesh):
            self.mesh = mesh
            self.gf = ngs.GridFunction(ngs.H1(mesh, order=2) * ngs.H1(mesh, order=1))
            self.u = self.gf.components[0]
            self.me = self

    mesh = ngs.Mesh(ngs.unit_square.GenerateMesh(maxh=0.3))
    solver = Solver(mesh)
    ws = Workspace()
    ws.add_namespace({"mesh": mesh, "solver": solver})
    ws.shown.value = True
    assert ws._by_name["solver"].members == ("solver.mesh", "solver.gf", "solver.u")
    assert ws._by_name["solver.gf"].members == ("solver.gf.components[0]", "solver.gf.components[1]")
    assert ws.get("solver.gf.components[1]") is solver.gf.components[1]
    # a stored component links to its function and is not counted again
    assert ("part of", "solver.gf", "solver.gf") in ws._by_name["solver.u"].details
    assert ws.memory("solver.u") == ws.memory("solver.gf") == (solver.gf.vec.size * 8, 0)
    # the mesh counts under its own name, the solver gets the rest
    _, _, rows = ws.memory_report()
    assert [r[0] for r in rows] == ["mesh", "solver"] and rows[1][2] == solver.gf.vec.size * 8
