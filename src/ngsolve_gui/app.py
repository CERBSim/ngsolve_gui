import os
import threading
import time

from ngapp.app import App
from ngapp.components import *

from .app_data import AppData
from .controls import ControlBar
from .file_loader import load_file
from ngapp.keybindings import KeybindingManager, keybinding_styles
from .navigator import Navigator
from .property_panel import empty_property_panel
from .prop_widgets import Segmented, on_cls
from .settings import usersettings as us
from . import cerbsim_style as cb
from .cerbsim_style import theme, kb_theme, flex_fill, panel_full
from .system_monitor import SystemMonitor, available as system_monitor_available
from .footer import StatusFooter
from .workspace.explorer import Explorer
from .workspace.ngsolve import region_marks


class TabHost(Div):
    """One row per tab, only the current one shown. Rows stay mounted: a
    remount costs a websocket round trip, for a viewport a canvas teardown."""

    def __init__(self, app_data, build, empty, **kwargs):
        current = app_data.current

        def row(uid):
            shown = computed(lambda: (c := current.value) is not None and c["uid"] == uid)
            return Show(shown, lambda: build(uid))

        super().__init__(
            For(computed(lambda: [t["uid"] for t in app_data.tabs.value]), row),
            Show(computed(lambda: current.value is None), empty),
            **kwargs,
        )


def _number(width, tip, ref, **kwargs):
    return QInput(QTooltip(tip), ui_type="number", ui_dense=True, ui_model_value=ref,
                  ui_style=f"width: {width}px;", **kwargs)


class Settings(QMenu):
    """Designer-styled settings dropdown (sections, segmented theme, switches)."""

    def __init__(self, app):
        ref = us.ref

        theme_seg = Segmented(
            [("light", "Light"), ("dark", "Dark"), ("system", "System")],
            ref("theme", "system"), lambda val: app._apply_theme(val),
        )
        colormap_select = QSelect(
            ui_options=[
                {"label": "Auto (theme)", "value": ""},
                "rainbow", "turbo", "viridis", "plasma", "cet_l20",
                "matlab:jet", "matplotlib:coolwarm",
            ],
            ui_model_value=ref("default_colormap", ""),
            ui_dense=True, ui_options_dense=True, ui_emit_value=True, ui_map_options=True,
            ui_style="width: 134px;",
        )
        ncolors = _number(72, "Number of color bands when colorbars are discrete.",
                          ref("default_ncolors", 8, int))
        vecdensity = _number(
            72, "Default arrow grid density for vector fields "
            "(cells across the longest domain side).",
            ref("default_vector_grid_size", 20, int))
        subdiv = _number(
            72, "Default subdivision for curved surface elements "
            "(-1 auto, 0 linear, higher = finer).", ref("default_subdivision", -1, int))
        subdiv3d = _number(
            72, "Default tessellation for curved 3D (volume) elements "
            "(-1 auto, 0 linear, higher = finer).",
            ref("default_elements3d_subdivision", -1, int))
        nthreads = _number(72, "Threads used by NGSolve (0 = all cores). Restart to apply.",
                           ref("nthreads", 0, int))
        redraw = _number(
            96, "Min milliseconds between redraws while a script runs (0 = no throttle).",
            ref("redraw_interval_ms", 50, int), ui_suffix="ms")
        gpu = QSelect(
            QTooltip("Preferred GPU adapter. Restart to apply."),
            ui_options=["high-performance", "low-power"],
            ui_model_value=ref("gpu_power_preference", "high-performance"),
            ui_dense=True, ui_options_dense=True, ui_emit_value=True,
            ui_style="width: 134px;",
        )

        timer_item = Div(
            QIcon(ui_name="mdi-timer-outline"), "Timer / profiling…",
            Div("diagnostics", ui_class=cb.menu_item_meta), ui_class=cb.menu_item,
        )
        timer_item.on("click", lambda e=None: app._open_timers())

        super().__init__(Div(
            Div("Appearance", ui_class=cb.menu_h),
            self._row("Theme", theme_seg),
            self._row("Default colormap", colormap_select),
            self._row("Discrete colormap", self._switch("default_discrete_colormap", False)),
            self._row("Default N colors", ncolors),
            Div(ui_class=cb.menu_sep),
            Div("Defaults", ui_class=cb.menu_h),
            self._row("Show axes", self._switch("axes_visible", True)),
            self._row("Show navigation cube", self._switch("navcube_visible", False)),
            self._row("Default vector density", vecdensity),
            Div(ui_class=cb.menu_sep),
            Div("Rendering", ui_class=cb.menu_h),
            self._row("Default subdivision", subdiv),
            self._row("Default 3D subdivision", subdiv3d),
            Div(ui_class=cb.menu_sep),
            Div("Performance", ui_class=cb.menu_h),
            self._row("Worker threads", nthreads),
            self._row("Redraw interval", redraw),
            self._row("GPU preference", gpu),
            Div(ui_class=cb.menu_sep),
            timer_item,
            ui_class=cb.menu_card,
        ))

    def _row(self, label, control):
        return Div(Div(label, ui_class=cb.menu_label), control, ui_class=cb.menu_row)

    def _switch(self, key, default):
        on = us.ref(key, default, bool)
        sw = Div(ui_class=on_cls(cb.prop_switch, cb.prop_switch_on, on))
        sw.on("click", lambda e=None: on.toggle())
        return sw


class NGSolveGui(App):
    def __init__(self, filename=None, local_path=None, script_args=None):
        self._local_path = local_path
        self.script_args = list(script_args or [])
        self.app_data = AppData()
        app_data = self.app_data
        self.workspace = app_data.workspace

        # -- Toolbar buttons (compact flat icon buttons, muted like the designer) --
        def _tbtn(icon, tip, handler=None):
            btn = QBtn(
                QTooltip(tip), ui_flat=True, ui_dense=True, ui_icon=icon,
                ui_class=str(cb.topbar_icon),
            )
            if handler is not None:
                btn.on_click(handler)
            return btn

        # File actions
        upload_file = _tbtn(
            "mdi-file-plus-outline", "Load file  ·  geometry / mesh / .py", self._load_file
        )
        savebtn = _tbtn("mdi-content-save-outline", "Save Project", self.save_local)
        loadbtn = _tbtn("mdi-folder-open-outline", "Load Project", self.load_local)
        file_group = Div(upload_file, savebtn, loadbtn, ui_class=cb.tb_group)

        settings_btn = QBtn(
            Settings(self), QTooltip("User Settings"),
            ui_flat=True, ui_dense=True, ui_icon="mdi-cog-outline",
            ui_class=str(cb.topbar_icon),
        )
        close_btn = _tbtn("mdi-close", "Quit", self.quit)
        close_btn.ui_class = str(cb.topbar_icon) + " " + str(cb.topbar_icon_danger)
        view_group = Div(settings_btn, close_btn, ui_class=cb.tb_group)

        ngs_logo = Div(
            QImg(
                ui_src=self.load_asset("ngsolve-mark.png"),
                ui_height="34px",
                ui_width="34px",
                ui_fit="contain",
            ),
            Div("Netgen / NGSolve", ui_class=cb.brand_wordmark),
            ui_class=cb.brand,
        )

        self.system_monitor = SystemMonitor() if system_monitor_available() else None

        # -- Redraw throttling state --
        from ngapp.utils import get_environment

        self._page = get_environment().page
        self._redraw_lock = threading.Lock()
        self._redraw_pending = False
        self._redraw_timer_running = False
        self._last_redraw_time = 0.0
        self._redraw_ms = us.ref("redraw_interval_ms", 50, int)

        bar = QBar(
            ngs_logo,
            file_group,
            QSpace(),
            *([self.system_monitor, Div(ui_class=cb.tb_sep)] if self.system_monitor is not None else []),
            view_group,
            ui_class=cb.app_bar,
        )

        self.kb = KeybindingManager(self, theme=kb_theme)
        self.navigator = Navigator(app_data, self._load_file, lambda query: Explorer(
            self.workspace, query, self._draw_object, self._highlight_region))
        # each component owns its property panel, the host shows the current one
        self.property_host = TabHost(
            app_data, self._property_panel, empty_property_panel, ui_class=panel_full)
        self.tab_host = TabHost(app_data, app_data.component, lambda: [], ui_class=panel_full)
        self.tab_host.effect(self._activate)
        self.controls = ControlBar()
        self.footer = StatusFooter(app_data, self.kb.mode)

        from .meshing_preview import install as _install_meshing_preview

        _install_meshing_preview(self)

        # Inner splitter: center | property panel (reverse so model = prop width)
        self._inner_splitter = self._splitter(
            "prop", 280,
            ui_reverse=True,
            ui_slots={
                "before": [Div(self.tab_host, ui_class=flex_fill)],
                "after": [self.property_host],
            },
            ui_class=cb.body_inner,
        )
        # Outer splitter: navigator | inner splitter
        self._outer_splitter = self._splitter(
            "nav", 200,
            ui_slots={
                "before": [self.navigator],
                "after": [self._inner_splitter],
            },
            ui_class=cb.body_fill,
        )

        # Timer / profiling diagnostics dialog (opened from the settings menu).
        self._timers = Observable((), "timers")
        timer_refresh = QBtn(QTooltip("Refresh"), ui_icon="mdi-refresh",
                             ui_flat=True, ui_dense=True, ui_round=True, ui_size="sm")
        timer_refresh.on_click(lambda *a: self._refresh_timers())
        self._timer_dialog = QDialog(QCard(
            Div(Div("Timer / profiling", ui_class=cb.prop_title_text), timer_refresh,
                ui_class=cb.prop_title),
            QSeparator(),
            Div(For(self._timers, self._timer_row, otherwise=lambda: Div(
                    "No timing data recorded yet.", ui_class=cb.hint,
                    ui_style="padding: 12px;")),
                ui_style="max-height: 56vh; overflow: auto; min-width: 400px;"
                         " padding: 4px 14px 12px;"),
            ui_class="cb-timer-card",
        ))

        super().__init__(
            bar, self._outer_splitter, self.controls, self.footer, self._timer_dialog,
            self.kb.indicator, self.kb.help_overlay,
            ui_class=str(cb.app_root),
        )

        cb.install(self, default_theme=us.get("theme", "system"))
        from .view.core import sync_default_viewport_clear
        sync_default_viewport_clear()
        keybinding_styles.inject(self)
        self.on_load(self.__on_load)

        # -- Global keybindings (always active) --
        kb = self.kb
        kb.add("h", kb.toggle_help, "Show keyboard shortcuts", "General")
        kb.add("ctrl+b", us.ref("nav_visible", True).toggle, "Toggle navigator", "Panels")
        kb.add("ctrl+alt+b", us.ref("prop_visible", True).toggle,
               "Toggle property panel", "Panels")
        for i in range(1, 10):
            kb.add(
                str(i),
                lambda n=i: self.navigator.select_by_index(n),
                f"Select item {i}",
                "Navigation",
            )
        self.add_keybinding("escape", lambda e: self.kb.on_escape())
        self.on_before_save(self.__on_before_save)
        if isinstance(filename, str):
            self._load_with_status(filename)
        elif isinstance(filename, list):
            for f in filename:
                self._load_with_status(f)

    @property
    def active_component(self):
        return self.app_data.active_component

    def _splitter(self, key, width, **kwargs):
        """A side panel splitter: the width is a user setting, a hidden panel
        has width 0 and cannot be dragged open."""
        visible = us.ref(f"{key}_visible", True)
        width = us.ref(f"{key}_width", width)
        split = Observable(width.value if visible.value else 0, f"{key}_split")
        visible.on_change(lambda v, _o: setattr(split, "value", width.value if v else 0))
        splitter = QSplitter(
            ui_model_value=split,
            ui_unit="px",
            ui_limits=computed(lambda: [0, 500] if visible.value else [0, 0]),
            ui_emit_immediately=True,
            **kwargs,
        )

        def resized(event):
            if int(event.value) > 0:
                width.value = int(event.value)

        splitter.on_update_model_value(resized)
        return splitter

    def _property_panel(self, uid):
        comp = self.app_data.component(uid)
        if hasattr(comp, "build_property_panel"):
            return comp.build_property_panel()
        return empty_property_panel()

    def _activate(self):
        """Point camera, key bindings at the current tab."""
        rec = self.app_data.current.value
        with untracked():
            comp = self.app_data.component(rec["uid"]) if rec is not None else None
            if comp is not None and hasattr(comp, "sync_camera"):
                comp.sync_camera()
            self.kb.set_component(comp)

    def _draw_object(self, name, mesh=None, title=None):
        import ngsolve

        obj = self.workspace.get(name)
        if obj is None:
            return
        if mesh is None:
            ngsolve.Draw(obj, name=title or name)
        elif (on := self.workspace.get(mesh)) is not None:
            ngsolve.Draw(obj, on, name=title or name)

    def _highlight_region(self, name, region):
        """Highlight a region of the mesh ``name`` if the current view shows it."""
        view = getattr(self.active_component, "view", None)
        picking = view.part("picking") if view is not None else None
        if picking is None:
            return
        mesh = self.workspace.get(name)
        shown = region is not None and getattr(self.active_component, "mesh", None) is mesh
        picking.mark_regions(region_marks(mesh, region[0], region[1]) if shown else {})

    def _load_file(self):
        from ngapp.utils import EnvironmentType, get_environment

        if get_environment().type == EnvironmentType.LOCAL_APP:
            from .native_dialog import open_file_dialog

            initialdir = (
                self._local_path
                or us.get("load_dir", "")
                or os.path.expanduser("~")
            )
            file_path = open_file_dialog(initialdir=initialdir)
            if file_path:
                self._local_path = os.path.dirname(file_path)
                us.set("load_dir", self._local_path)
        else:
            file_path = self._pick_file_to_temp()
        self._load_with_status(file_path)

    def _pick_file_to_temp(self):
        """Browser-picker fallback: the File System Access API only hands us the
        file's content and name (never a real path), so materialise it in a temp
        dir keeping the original name (preserves multi-part suffixes like
        .vol.gz that the loader dispatches on)."""
        import tempfile

        try:
            handles = self.js.showOpenFilePicker({"multiple": False})
        except Exception:
            return None
        if not handles:
            return None
        js_file = handles[0].getFile()
        tmpdir = tempfile.mkdtemp(prefix="ngsolve_gui_")
        file_path = os.path.join(tmpdir, js_file.name)
        with open(file_path, "wb") as f:
            f.write(js_file.arrayBuffer())
        return file_path

    def _load_with_status(self, filename):
        if not filename:
            return
        self.controls.clear()
        result = load_file(filename, self)
        if result:
            thread, done_event = result
            name = os.path.basename(str(filename))
            self.footer.show(name, thread, done_event)

    def __on_before_save(self):
        self.storage.set("app_data", self.app_data.get_save_data(), use_pickle=True)

    def __on_load(self):
        data = self.storage.get("app_data")
        if data is not None:
            self.app_data.load_save_data(data)

    def _open_timers(self):
        self._refresh_timers()
        self._timer_dialog.ui_model_value = True

    def _refresh_timers(self):
        try:
            import ngsolve
            timers = sorted(ngsolve.Timers(), key=lambda t: -t.get("time", 0.0))[:40]
        except Exception:
            timers = []
        self._timers.value = tuple((t.get("name", ""), t.get("time", 0.0)) for t in timers)

    @staticmethod
    def _timer_row(timer):
        name, time_ = timer
        return Div(
            Div(name, ui_class="ellipsis", ui_style="flex: 1; min-width: 0;"),
            Div(f"{time_:.4f} s", ui_class=cb.mono, ui_style="flex: none;"),
            ui_class="row items-center no-wrap " + str(cb.gap_sm),
            ui_style="padding: 4px 2px; border-bottom: 1px solid var(--border-faint);"
                     " font-size: 12px;",
        )

    def _apply_theme(self, val):
        """Theme of the page and the scene background of every open 3D tab."""
        cb.set_theme(self, val)
        from .view.core import sync_default_viewport_clear
        sync_default_viewport_clear()  # so tabs opened later also start correct
        for comp in list(self.app_data._components.values()):
            if hasattr(comp, "apply_viewport_theme"):
                comp.apply_viewport_theme()

    def redraw(self, *args, **kwargs):
        self._page_alive()
        self.app_data.set_needs_redraw()
        self._request_redraw()

    def _request_redraw(self):
        """Coalesce rapid redraw calls into at most one actual redraw per interval.

        When a Python script calls ngs.Redraw() in a tight loop (e.g. time-stepping),
        this avoids blocking the script thread and flooding the GPU with renders.

        The trailing-edge timer guarantees the *last* requested redraw is always
        rendered, even if no further calls arrive.
        """
        interval = max(0, self._redraw_ms.value) / 1000.0
        if interval <= 0:
            # No throttling — redraw immediately on every call.
            self._do_redraw()
            return

        now = time.monotonic()
        with self._redraw_lock:
            self._redraw_pending = True
            elapsed = now - self._last_redraw_time
            if elapsed >= interval:
                # Enough time passed — redraw immediately (leading edge).
                self._do_redraw()
            elif not self._redraw_timer_running:
                # Schedule a trailing-edge timer so the last redraw is never lost.
                self._redraw_timer_running = True
                delay = interval - elapsed
                threading.Timer(delay, self._deferred_redraw).start()

    def _deferred_redraw(self):
        """Trailing-edge timer callback — guarantees the final redraw fires."""
        with self._redraw_lock:
            self._redraw_timer_running = False
            if self._redraw_pending:
                self._do_redraw()

    def _do_redraw(self):
        """Actually perform the redraw (must be called with _redraw_lock held, or interval=0)."""
        self._redraw_pending = False
        self._last_redraw_time = time.monotonic()
        comp = self.active_component
        if comp is None or not hasattr(comp, "redraw") or not self._page_alive():
            return
        try:
            comp.redraw()
        except Exception:
            # the page closed mid-render: the app exits soon or is replaced
            if self._page_alive():
                raise

    def _page_alive(self):
        """False while no page is connected (the app exits soon). A reload
        runs the script again in a new app, the script of this one ends."""
        from ngapp.utils import get_environment
        from webgpu import platform

        if get_environment().page != self._page:
            raise SystemExit
        link = getattr(platform, "websocket_server", None)
        return link is None or getattr(link, "is_connected", True)
