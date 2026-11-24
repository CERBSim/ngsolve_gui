"""Live surface-mesh preview during meshing.

How it works:

* `GenerateMesh` on the geometry classes is monkey-patched. Whenever it runs
  and a geometry tab is currently shown, its `meshing_preview` layer is fed for the
  duration of the call. This covers both the "Generate mesh" button (whose
  `create_mesh` calls `GenerateMesh`) *and* any user script that calls
  `geo.GenerateMesh(...)` after `Draw(geo)`.
"""

from .view.ngsolve.preview import get_terminate, set_terminate  # noqa: F401

_app = None
_patched = False

_originals: dict = {}

_last_interaction = 0.0

def install(app):
    """Register the running app and monkey-patch GenerateMesh (idempotent)."""
    global _app, _patched
    _app = app
    if _patched:
        return
    _patch_generate_mesh()
    _patch_camera_interaction()
    _patched = True


def _patch_camera_interaction():
    """Record interaction time whenever the JS engine reports a camera move.

    Rotation/zoom is handled entirely JS-side (Scene._apply_camera_from_js only
    mirrors the matrix into Python, it does not re-render). We hook it to know
    when the user is actively interacting so the preview can hold its updates and
    not ship structural engine.update()s into the middle of a JS render frame —
    that race is what flickers between the geometry and the mesh while rotating.

    Patched at the class level at app startup, before any scene creates its
    camera-changed proxy, so the proxy binds this wrapped version.
    """
    try:
        from webgpu.scene import Scene
    except Exception:
        return
    if getattr(Scene, "_meshing_preview_cam_patched", False):
        return
    orig = Scene._apply_camera_from_js

    def wrapped(self, payload):
        global _last_interaction
        import time

        _last_interaction = time.monotonic()
        return orig(self, payload)

    Scene._apply_camera_from_js = wrapped
    Scene._meshing_preview_cam_patched = True


def get_app():
    return _app


def _candidate_geometry_classes():
    """The geometry classes whose GenerateMesh we want to wrap."""
    classes = []
    try:
        import netgen.occ as ngocc

        classes.append(ngocc.OCCGeometry)
    except Exception:
        pass
    # Other geometry kinds share the same Python-level method name; wrap them too
    # when present so scripts using them also get a preview.
    for modname, clsname in (
        ("netgen.csg", "CSGeometry"),
        ("netgen.stl", "STLGeometry"),
        ("netgen.geom2d", "SplineGeometry"),
    ):
        try:
            mod = __import__(modname, fromlist=[clsname])
            cls = getattr(mod, clsname, None)
            if cls is not None and hasattr(cls, "GenerateMesh"):
                classes.append(cls)
        except Exception:
            pass
    return classes


def _patch_generate_mesh():
    for cls in _candidate_geometry_classes():
        orig = cls.__dict__.get("GenerateMesh", None) or getattr(cls, "GenerateMesh", None)
        if orig is None or cls in _originals:
            continue
        _originals[cls] = orig
        cls.GenerateMesh = _make_wrapper(cls, orig)


def _make_wrapper(cls, orig):
    def generate_mesh(self, *args, **kwargs):
        preview = _try_start_preview()
        if preview is None:
            return orig(self, *args, **kwargs)

        if args:
            return orig(self, *args, **kwargs)

        mesh = kwargs.get("mesh")
        if mesh is None:
            import netgen.meshing as ngm

            mesh = ngm.Mesh()
            kwargs["mesh"] = mesh

        set_terminate(False)
        preview.bind(mesh)
        try:
            ret = orig(self, *args, **kwargs)
        finally:
            preview.stop()
        return ret if ret is not None else mesh

    generate_mesh.__name__ = getattr(orig, "__name__", "GenerateMesh")
    generate_mesh.__doc__ = getattr(orig, "__doc__", None)
    return generate_mesh


def _try_start_preview():
    """A poller showing the mesh in the active tab's preview layer, or None."""
    app = _app
    if app is None:
        return None
    try:
        comp = app.active_component
        layer = comp.view.part("meshing_preview")
    except Exception:
        return None
    if layer is None or comp.view.scene is None:
        return None
    from .view.ngsolve.preview import PreviewPoller

    return PreviewPoller(layer, lambda: _last_interaction)
