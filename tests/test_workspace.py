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
