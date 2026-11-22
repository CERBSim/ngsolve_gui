"""Small toolbar widget that displays live CPU, RAM, and GPU usage with mini bars."""

import os
import subprocess
import threading
import time

from ngapp.components import Div, Observable, QIcon, QLinearProgress, computed
from ngapp.utils import get_environment

from .cerbsim_style import (
    monitor,
    monitor_icon,
    monitor_body,
    monitor_label,
    monitor_value,
    monitor_subvalue,
    monitor_stat,
    monitor_stat_header,
    monitor_bars,
    monitor_bar,
    monitor_subbar,
)


# ── Cached constants (set once, never change) ────────────────────────────────
_pid = os.getpid()

# psutil state (populated by _ensure_psutil)
_psutil = None          # module ref
_cpu_count = None
_process = None         # psutil.Process for current pid
_psutil_tried = False

# pynvml state (populated by _ensure_nvml)
_nvml_handle = None
_nvml_tried = False
_nvml_ready = False
_nvml_get_mem_info = None
_nvml_get_util = None
_nvml_get_compute_procs = None
_nvml_get_graphics_procs = None

# nvidia-smi fallback
_nvidia_smi_available = None


def _ensure_psutil():
    """Import psutil once, cache module ref, cpu_count and Process handle."""
    global _psutil, _cpu_count, _process, _psutil_tried
    if _psutil_tried:
        return _psutil is not None
    _psutil_tried = True
    try:
        import psutil
        _psutil = psutil
        _cpu_count = psutil.cpu_count() or 1
        _process = psutil.Process(_pid)
        # Seed both cpu_percent counters so first real read is meaningful
        psutil.cpu_percent(interval=None)
        _process.cpu_percent(interval=None)
        return True
    except ImportError:
        return False


def available():
    """System monitor needs psutil (not available e.g. in pyodide)."""
    return _ensure_psutil()


def _ensure_nvml():
    """Initialise pynvml once, cache device handle and function references."""
    global _nvml_tried, _nvml_ready, _nvml_handle
    global _nvml_get_mem_info, _nvml_get_util
    global _nvml_get_compute_procs, _nvml_get_graphics_procs
    if _nvml_tried:
        return _nvml_ready
    _nvml_tried = True
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import pynvml
        pynvml.nvmlInit()
        _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        _nvml_get_mem_info = pynvml.nvmlDeviceGetMemoryInfo
        _nvml_get_util = pynvml.nvmlDeviceGetUtilizationRates
        _nvml_ready = True
        # Per-process helpers (may not exist in older pynvml)
        try:
            _nvml_get_compute_procs = pynvml.nvmlDeviceGetComputeRunningProcesses
        except AttributeError:
            pass
        try:
            _nvml_get_graphics_procs = pynvml.nvmlDeviceGetGraphicsRunningProcesses
        except AttributeError:
            pass
    except Exception:
        _nvml_ready = False
    return _nvml_ready


def _get_stats(include_proc_gpu):
    """Gather system and per-process stats.

    *include_proc_gpu* controls whether the (moderately expensive)
    per-process GPU memory query is performed this tick.
    """
    global _nvidia_smi_available
    stats = {}

    # ── CPU & RAM (system + process) ─────────────────────────────────────
    if _ensure_psutil():
        stats["cpu"] = _psutil.cpu_percent(interval=None)
        mem = _psutil.virtual_memory()
        stats["ram_used_gb"] = mem.used / (1024**3)
        stats["ram_total_gb"] = mem.total / (1024**3)
        stats["ram_percent"] = mem.percent

        try:
            stats["proc_cpu"] = _process.cpu_percent(interval=None) / _cpu_count
            rss = _process.memory_info().rss
            stats["proc_ram_gb"] = rss / (1024**3)
        except Exception:
            pass

    # ── GPU (pynvml fast-path) ───────────────────────────────────────────
    if _ensure_nvml():
        try:
            mem_info = _nvml_get_mem_info(_nvml_handle)
            util = _nvml_get_util(_nvml_handle)
            stats["gpu_used_gb"] = mem_info.used / (1024**3)
            stats["gpu_total_gb"] = mem_info.total / (1024**3)
            stats["gpu_util"] = util.gpu
        except Exception:
            pass

        # Per-process VRAM (only on selected ticks)
        if include_proc_gpu:
            try:
                for fn in (_nvml_get_compute_procs, _nvml_get_graphics_procs):
                    if fn is None:
                        continue
                    for p in fn(_nvml_handle):
                        if p.pid == _pid:
                            stats["proc_gpu_mem_gb"] = p.usedGpuMemory / (1024**3)
                            break
                    if "proc_gpu_mem_gb" in stats:
                        break
            except Exception:
                pass
    else:
        # ── nvidia-smi fallback ──────────────────────────────────────────
        if _nvidia_smi_available is not False:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi",
                     "--query-gpu=utilization.gpu,memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    timeout=2, stderr=subprocess.DEVNULL,
                ).decode().strip()
                parts = [p.strip() for p in out.split(",")]
                if len(parts) == 3:
                    stats["gpu_util"] = int(parts[0])
                    stats["gpu_used_gb"] = float(parts[1]) / 1024
                    stats["gpu_total_gb"] = float(parts[2]) / 1024
                    _nvidia_smi_available = True
            except Exception:
                _nvidia_smi_available = False

    return stats


# Quasar brand color names, resolved by the theme to semantic colors.
def _color_for_percent(pct):
    if pct < 50:
        return "positive"
    if pct < 80:
        return "warning"
    return "negative"


def _proc_color_for_percent(pct):
    """Accent colours for the per-process sub-bar."""
    if pct < 50:
        return "info"
    if pct < 80:
        return "warning"
    return "negative"


def _cpu(stats):
    if "cpu" not in stats:
        return None
    pct, proc = stats["cpu"], stats.get("proc_cpu")
    return (f"{pct:.0f}%", pct / 100, _color_for_percent(pct),
            f"{proc:.0f}%" if proc is not None else None,
            proc / 100 if proc is not None else None)


def _ram(stats):
    if "ram_used_gb" not in stats:
        return None
    used, total, proc = stats["ram_used_gb"], stats["ram_total_gb"], stats.get("proc_ram_gb")
    return (f"{used:.1f}/{total:.0f}G", stats["ram_percent"] / 100,
            _color_for_percent(stats["ram_percent"]),
            f"{proc:.1f}G" if proc is not None else None,
            proc / total if proc is not None and total > 0 else None)


def _gpu(stats):
    if "gpu_util" not in stats:
        return ("N/A", 0, "grey-5", None, None)
    pct = stats["gpu_util"]
    return (f"{pct}%", pct / 100, _color_for_percent(pct), None, None)


def _vram(stats):
    if "gpu_used_gb" not in stats:
        return ("N/A", 0, "grey-5", None, None)
    used, total, proc = stats["gpu_used_gb"], stats["gpu_total_gb"], stats.get("proc_gpu_mem_gb")
    pct = (used / total * 100) if total > 0 else 0
    return (f"{used:.1f}/{total:.0f}G", pct / 100, _color_for_percent(pct),
            f"{proc:.1f}G" if proc is not None else None,
            proc / total if proc is not None and total > 0 else None)


class _StatBar(Div):
    """A labeled mini-bar of one metric with an optional process sub-bar.

    *read* maps the stats to (text, fraction, color, proc_text, proc_fraction)
    or None (no data yet)."""

    def __init__(self, label, icon_name, stats, read):
        val = computed(lambda: read(stats.value) or ("\u2014", 0, "positive", None, None))
        proc = computed(lambda: max(0.0, min(1.0, val.value[4] or 0)))
        bar = QLinearProgress(
            ui_value=computed(lambda: max(0.0, min(1.0, val.value[1]))),
            ui_color=computed(lambda: val.value[2]),
            ui_track_color="grey-3",
            ui_class=monitor_bar,
            ui_rounded=True,
        )
        proc_bar = QLinearProgress(
            ui_value=computed(lambda: proc.value if val.value[3] is not None else 0),
            ui_color=computed(lambda: _proc_color_for_percent(proc.value * 100)),
            ui_track_color="grey-3",
            ui_class=monitor_subbar,
            ui_rounded=True,
        )

        icon = QIcon(ui_name=icon_name, ui_size="14px", ui_class=monitor_icon)
        # value + per-process sub-value share the right side of the header row
        value_group = Div(
            Div(computed(lambda: val.value[0]), ui_class=monitor_value),
            Div(computed(lambda: f"({val.value[3]})" if val.value[3] is not None else ""),
                ui_class=monitor_subvalue),
            ui_class="row items-baseline q-gutter-x-xs",
        )
        header = Div(
            Div(label, ui_class=monitor_label),
            value_group,
            ui_class=monitor_stat_header,
        )
        body = Div(
            header,
            Div(bar, proc_bar, ui_class=monitor_bars),
            ui_class=monitor_body,
        )
        super().__init__(icon, body, ui_class=monitor_stat)


class SystemMonitor(Div):
    """Compact system stats display for the toolbar with mini progress bars."""

    def __init__(self, update_interval=1.0):
        self._interval = update_interval
        self.stats = Observable({}, "system_stats")
        super().__init__(
            _StatBar("CPU", "mdi-chip", self.stats, _cpu),
            _StatBar("RAM", "mdi-memory", self.stats, _ram),
            _StatBar("GPU", "mdi-expansion-card", self.stats, _gpu),
            _StatBar("VRAM", "mdi-expansion-card-variant", self.stats, _vram),
            ui_class=monitor,
        )

        self._running = True
        self._tick = 0
        self._last_proc_vram = None  # cache last known per-process VRAM
        # Trigger one-time init (seeds cpu_percent counters)
        _ensure_psutil()
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        while self._running:
            time.sleep(self._interval)
            # a page reload shows a new app instance
            app = self.app
            if app is not None and getattr(get_environment().frontend, "app", app) is not app:
                return
            # Per-process GPU query every other tick (every ~2s)
            include_proc_gpu = (self._tick % 2 == 0)
            self._tick += 1
            stats = _get_stats(include_proc_gpu)
            if "proc_gpu_mem_gb" in stats:
                self._last_proc_vram = stats["proc_gpu_mem_gb"]
            elif self._last_proc_vram is not None:
                stats["proc_gpu_mem_gb"] = self._last_proc_vram
            self.stats.value = stats

    def stop(self):
        self._running = False
