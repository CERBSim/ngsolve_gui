"""Bottom status bar: live run status (left), quick stats, viewport mode.

The leftmost item doubles as the loading indicator: it shows "Ready" when idle
and, while a script/mesh job runs, the live status text polled from netgen plus
an inline progress bar and a cancel button.
"""

import ctypes
import threading
import time

from ngapp.components import (
    Div, For, Observable, QBtn, QIcon, QSpinner, QTooltip, batch, computed, untracked,
)

from .cerbsim_style import (
    statusbar,
    status_item,
    status_num,
    status_spacer,
    status_mode,
    status_chip,
    status_chip_ready,
    status_dot,
    status_dot_ready,
    status_track_inline,
    status_fill,
    status_fill_indeterminate,
    status_text as status_text_cls,
    mono,
    hint,
    gap_sm,
)


def _fmt(n):
    """Group thousands with thin spaces for readable counts."""
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


class StatusFooter(Div):
    """The poll thread only writes ``_task``/``_status``/``_percent``; stats
    follow the current tab, the mode follows the key binding manager."""

    def __init__(self, app_data, mode):
        self.app_data = app_data
        self._busy = Observable(False, "status_busy")
        self._status = Observable("", "status_text")
        self._percent = Observable(None, "status_percent")  # None: indeterminate

        idle = Div(
            Div(ui_class=str(status_dot) + " " + str(status_dot_ready)),
            "Ready",
            ui_class=str(status_chip) + " " + str(status_chip_ready),
            ui_hidden=self._busy,
        )
        pct = self._percent
        bar_fill = Div(
            ui_class=computed(lambda: str(
                status_fill_indeterminate if pct.value is None else status_fill)),
            ui_style=computed(lambda: "" if pct.value is None else f"width: {pct.value:.1f}%;"),
        )
        cancel_btn = QBtn(
            QTooltip("Cancel"),
            ui_icon="mdi-close", ui_flat=True, ui_dense=True, ui_round=True,
            ui_size="xs", ui_padding="2px",
        )
        cancel_btn.on_click(self._on_cancel)
        busy = Div(
            QSpinner(ui_color="primary", ui_size="14px"),
            Div(self._status, ui_class=status_text_cls),
            Div(bar_fill, ui_class=status_track_inline),
            Div(computed(lambda: "" if pct.value is None else f"{pct.value:.0f}%"),
                ui_class=str(mono) + " " + str(hint)),
            cancel_btn,
            ui_class="row items-center no-wrap " + str(gap_sm),
            ui_hidden=computed(lambda: not self._busy.value),
        )

        mode_section = Div(
            QIcon(ui_name="mdi-keyboard-outline", ui_size="13px"),
            Div(computed(lambda: f"{mode.value} mode"), ui_class=status_mode),
            ui_class=status_item,
            ui_hidden=computed(lambda: not mode.value),
        )

        # Polling state (mirrors the old floating status pill).
        self._thread = None
        self._thread_name = ""
        self._done_event = None
        self._generation = 0
        self._task_label = None

        super().__init__(
            Div(idle, busy, ui_class=status_item),
            Div(For(computed(self._stats), self._stat), ui_class="row items-center no-wrap"),
            Div(ui_class=status_spacer),
            mode_section,
            ui_class=statusbar,
        )

    # -- active object -------------------------------------------------
    def _stats(self):
        rec = self.app_data.current.value
        if rec is None:
            return ()
        with untracked():
            return tuple(self._stats_for(self.app_data.component(rec["uid"]), rec["type"]))

    @staticmethod
    def _stat(stat):
        label, value = stat
        return Div(label, Div(value, ui_class=status_num), ui_class=status_item)

    @staticmethod
    def _stats_for(comp, type_key):
        """Best-effort quick stats read directly off the active component."""
        try:
            if type_key == "geometry":
                geo = comp.geo
                out = []
                try:
                    out.append(("Solids", _fmt(len(geo.shape.solids))))
                except Exception:
                    pass
                out.append(("Faces", _fmt(len(geo.faces))))
                out.append(("Edges", _fmt(len(geo.edges))))
                return out
            if type_key == "mesh":
                import ngsolve as ngs
                m = comp.mesh
                return [
                    ("VOL", _fmt(m.GetNE(ngs.VOL))),
                    ("BND", _fmt(m.GetNE(ngs.BND))),
                    ("Points", _fmt(m.nv)),
                    ("Dim", f"{m.dim}D"),
                ]
            if type_key == "function":
                import ngsolve as ngs
                out = []
                cf = comp.cf
                if isinstance(cf, ngs.GridFunction):
                    try:
                        out.append(("DOF", _fmt(cf.space.ndof)))
                    except Exception:
                        pass
                dim = getattr(cf, "dim", 1)
                out.append(("Components", str(dim)))
                out.append(("Dim", f"{comp.mesh.dim}D"))
                return out
            if type_key == "plot":
                return [("Type", "plot"), ("Renderer", "Plotly")]
        except Exception:
            pass
        return []

    # -- run status (busy) ---------------------------------------------
    def show(self, filename, thread, done_event):
        """Enter the busy state and start polling netgen for live status."""
        self._generation += 1
        self._thread = thread
        self._done_event = done_event
        self._thread_name = thread.name if thread else ""
        self._task_label = None
        with batch():
            self._status.value = f"Running {filename} …"
            self._percent.value = None
            self._busy.value = True
        self._start_poll(self._generation)

    def set_task(self, label):
        """Set a high-level task label shown in preference to the kernel status
        (e.g. 'Merging into the neighbouring face…'). Cleared on the next op."""
        self._task_label = label or None

    def hide(self):
        """Return to the idle 'Ready' state."""
        self._thread = None
        self._done_event = None
        self._task_label = None
        self._busy.value = False

    def _start_poll(self, gen):
        def poll():
            from netgen.libngpy._meshing import _GetStatus

            while gen == self._generation:
                time.sleep(0.3)
                done_event = self._done_event
                if done_event is None:
                    break
                try:
                    status_text, percent = _GetStatus()
                except Exception:
                    status_text, percent = "idle", 0.0
                text = self._task_label or (status_text if status_text != "idle" else "")
                if text:
                    with batch():
                        self._status.value = text
                        self._percent.value = max(0.0, min(100.0, percent)) if percent > 0 else None
                if done_event.is_set():
                    self.hide()
                    break

        threading.Thread(target=poll, daemon=True, name="StatusPoll").start()

    def _on_cancel(self):
        self._generation += 1
        try:
            from .view.ngsolve.preview import set_terminate

            set_terminate(True)
        except Exception:
            pass
        thread = self._thread
        if thread and thread.is_alive() and self._thread_name != "IPythonEmbedder":
            try:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(thread.ident),
                    ctypes.py_object(KeyboardInterrupt),
                )
            except Exception:
                pass
        self.hide()
