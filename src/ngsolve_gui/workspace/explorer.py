"""Object explorer: the workspace entries, listed in the navigator."""

from ngapp.components import *

from .. import cerbsim_style as cb
from . import format_bytes
from ..view.core.widgets import on_cls

_TOP = 8
_CHIP = ("display: inline-block; padding: 0 6px; margin: 2px 4px 0 0; cursor: default;"
         " border-radius: var(--r-pill); font-size: 11px; border: 1px solid var(--border);")


class Explorer(Div):
    """``on_draw(name, mesh=None, title=None)`` opens a view of an object (on
    the mesh or region ``mesh``), ``on_highlight(name, region)`` highlights a region
    of a mesh in the current view (None clears). Folded, the workspace is
    not scanned."""

    def __init__(self, workspace, query, on_draw, on_highlight):
        self._on_draw, self._on_highlight = on_draw, on_highlight
        self._workspace = workspace
        self._open = Observable(None, "explorer_open")
        self._entries = workspace.entries
        shown = workspace.shown
        collapsed = computed(lambda: not shown.value)
        self._by_name = computed(lambda: {e.name: e for e in workspace.entries.value})

        def matching():
            entries = workspace.entries.value
            if not query.value:
                return tuple(e for e in entries if e.parent is None)
            roots = {_root(e.name) for e in entries if query.value in e.name.lower()}
            return tuple(e for e in entries if e.parent is None and e.name in roots)
        matches = computed(matching)

        refresh = QBtn(QTooltip("Rescan the script variables"), ui_flat=True, ui_dense=True,
                       ui_round=True, ui_size="xs", ui_icon="mdi-refresh", ui_color="grey-7")
        refresh.on_click(lambda *a: workspace.refresh())
        report = Observable(None, "memory_report")
        memory_open = Observable(False, "memory_open")
        memory = QBtn(QTooltip("Memory used by the objects"), ui_flat=True, ui_dense=True,
                      ui_round=True, ui_size="xs", ui_icon="mdi-memory", ui_color="grey-7")

        def open_memory(*a):
            workspace.shown.value = True
            report.value = workspace.memory_report()
            memory_open.value = True
        memory.on_click(open_memory)
        dialog = QDialog(QCard(
            Div(Div("Memory", ui_class=cb.prop_title_text), ui_class=cb.prop_title),
            QSeparator(),
            Div(Dynamic(lambda: _memory_view(*report.value) if report.value else None),
                ui_style="max-height: 60vh; overflow: auto; min-width: 440px;"
                         " padding: 4px 14px 12px;"),
        ), ui_model_value=memory_open)
        toggle = Div(
            QIcon(ui_name="mdi-chevron-down", ui_size="16px", ui_class=on_cls(
                cb.nav_group_caret, cb.nav_group_caret_collapsed, collapsed)),
            QIcon(ui_name="mdi-code-braces", ui_size="15px"),
            Div("Workspace", ui_class=cb.nav_group_name),
            Show(shown, lambda: Div(computed(lambda: str(sum(
                e.parent is None for e in workspace.entries.value))),
                                    ui_class=cb.nav_count_badge)),
            ui_class="row items-center no-wrap " + str(cb.grow), ui_style="gap: 7px;",
        )
        toggle.on("click", lambda e=None: shown.toggle())
        items = computed(lambda: () if collapsed.value else matches.value)
        super().__init__(
            Div(toggle, memory, refresh, ui_class=cb.nav_group_row), dialog,
            Show(computed(lambda: not collapsed.value and not matches.value),
                 lambda: Div("No objects. Variables of a loaded script appear here.",
                             ui_class=cb.nav_empty)),
            For(items, self._item, key=lambda e: e.name, reactive=True),
        )

    def _item(self, entry):
        """An entry; open while it or one of its members is open (a member
        named ``solver.a`` opens with ``solver``)."""
        name, parent = entry.peek().name, entry.peek().parent
        label = name[len(parent):].lstrip(".") if parent else name
        head = Div(
            QIcon(ui_name=computed(lambda: entry.value.icon), ui_size="xs", ui_color="grey-7"),
            Div(label, ui_class="ellipsis " + str(cb.grow)),
            Div(computed(lambda: entry.value.kind), ui_class=cb.hint, ui_style="font-size: 11px;"),
            ui_class="row items-center no-wrap " + str(cb.gap_sm), ui_style="cursor: pointer;",
        )
        is_open = computed(lambda: _within(self._open.value, name))
        head.on("click", lambda e=None: setattr(
            self._open, "value", parent if is_open.value else name))
        return Div(head, Show(is_open, lambda: self._details(entry, name)),
                   ui_class=cb.nav_item if parent is None else None)

    def _details(self, entry, name):
        def row(detail):
            label, value, ref = detail
            shown = Div(str(value), ui_class=cb.mono)
            if ref is not None:
                shown.ui_style = "color: var(--accent); cursor: pointer;"
                shown.on("click", lambda e=None: setattr(self._open, "value", ref))
            return Div(Div(label, ui_class=cb.hint, ui_style="flex: 1;"), shown,
                       ui_class="row items-center no-wrap")

        def chip(region):
            c = Div(region[2], ui_style=_CHIP)
            c.on("mouseenter", lambda e=None: self._on_highlight(name, region))
            c.on("mouseleave", lambda e=None: self._on_highlight(name, None))
            return c

        def regions(kind, label):
            items = computed(lambda: tuple(r for r in entry.value.regions if r[0] == kind))
            return Show(computed(lambda: bool(items.value)), lambda: Div(
                Div(label, ui_class=cb.hint), For(items, chip), ui_style="margin-top: 4px;"))

        def btn(label, tip, on_click):
            b = QBtn(QTooltip(tip), ui_label=label, ui_icon="mdi-eye-outline", ui_flat=True,
                     ui_dense=True, ui_size="sm", ui_color="primary")
            b.on_click(lambda *a: on_click())
            return b

        def targets():
            """Meshes and regions to draw a function on; the default first:
            the last one defined before the function."""
            fn, entries = entry.value, self._entries.value
            first = {}
            for e in entries:
                if e.target and (fn.mesh_id is None or e.mesh_id == fn.mesh_id):
                    first.setdefault(e.ident, e.name)
            fits = list(first.values())
            before = [e.name for e in entries[:entries.index(fn)] if e.name in fits] \
                if fn in entries else []
            default = before[-1] if before else (fits[0] if fits else None)
            return tuple([default] + [n for n in fits if n != default]) if fits else ()

        options = computed(targets)
        chosen = Observable(None, "draw_on_target")
        target = computed(lambda: chosen.value if chosen.value in options.value
                          else (options.value[0] if options.value else None))
        select = QSelect(ui_options=options, ui_model_value=target, ui_dense=True,
                         ui_options_dense=True, ui_borderless=True,
                         ui_style="min-width: 70px; font-size: 12px;")
        select.on_update_model_value(lambda e: setattr(chosen, "value", e.value))

        def draw_on_target():
            mesh = target.value
            self._on_draw(name, mesh, name if mesh == options.value[0] else f"{name} on {mesh}")

        draw_on = Div(btn("Draw on", "Open a view on the chosen mesh or region", draw_on_target),
                      select, ui_class="row items-center no-wrap " + str(cb.gap_xs))

        memory = () if self._workspace.part_of(name) else tuple(
            (label, format_bytes(n), None) for label, n
            in zip(("RAM", "VRAM"), self._workspace.memory(name)) if n)
        members = computed(lambda: tuple(self._by_name.value[n] for n in entry.value.members
                                         if n in self._by_name.value))
        return Div(
            For(computed(lambda: entry.value.details + memory), row),
            For(members, self._item, key=lambda e: e.name, reactive=True),
            regions("material", "Materials"),
            regions("boundary", "Boundaries"),
            Show(computed(lambda: entry.value.on_mesh and bool(options.value)), lambda: draw_on,
                 otherwise=lambda: Show(computed(lambda: entry.value.drawable), lambda: btn(
                     "Draw", "Open a view", lambda: self._on_draw(name)))),
            ui_style="padding: 4px 0 4px 22px; font-size: 12px;",
        )


def _root(name):
    return name.split(".", 1)[0].split("[", 1)[0]


def _within(opened, name):
    """``opened`` is ``name`` or one of its members."""
    return opened is not None and opened.startswith(name) and (
        len(opened) == len(name) or opened[len(name)] in ".[")


def _memory_view(ram, vram, rows):
    sections = [_shares("RAM", [(n, k, r) for n, k, r, _ in rows], ram)]
    if vram is not None:
        sections.append(_shares("VRAM", [(n, k, v) for n, k, _, v in rows], vram,
                                ("views", "renderers, overlays")))
    return Div(*sections, Div("Estimates. RAM of meshes is guessed from the element count,"
                              " VRAM counts buffers of what is drawn.",
                              ui_class=cb.hint, ui_style="margin-top: 10px;"))


def _shares(title, rows, total, other=None):
    """Bars of the largest objects and the rest; ``other`` names a bar for
    what no object accounts for, else the total is only given in the head."""
    rows = sorted((r for r in rows if r[2]), key=lambda r: -r[2])
    attributed = sum(r[2] for r in rows)
    bars = rows[:_TOP]
    if len(rows) > _TOP:
        bars.append(("rest", f"{len(rows) - _TOP} objects", sum(r[2] for r in rows[_TOP:])))
    total = max(total or 0, attributed)
    scale = attributed
    if other is not None and total > attributed:
        bars.append((*other, total - attributed))
        scale = total
        summary = format_bytes(total)
    else:
        summary = f"objects {format_bytes(attributed)} of {format_bytes(total)} process" \
            if total > attributed else format_bytes(attributed)

    def bar(row):
        name, kind, n = row
        color = "var(--accent)" if row in rows else "var(--border)"
        return Div(
            Div(name, ui_class="ellipsis", ui_style="width: 110px;"),
            Div(kind, ui_class=cb.hint + " ellipsis", ui_style="width: 110px; font-size: 11px;"),
            Div(Div(ui_style=f"height: 8px; border-radius: 4px; background: {color};"
                             f" width: max(2px, {100 * n / scale:.1f}%);"),
                ui_style="flex: 1; margin: 0 8px;"),
            Div(format_bytes(n), ui_class=cb.mono, ui_style="width: 64px; text-align: right;"),
            ui_class="row items-center no-wrap", ui_style="padding: 2px 0; font-size: 12px;")

    head = Div(Div(title, ui_style="font-weight: 600; flex: 1;"),
               Div(summary if total else "", ui_class=cb.hint),
               ui_class="row items-center", ui_style="margin: 10px 0 4px;")
    if not bars:
        return Div(head, Div("Nothing drawn yet." if title == "VRAM" else "No objects.",
                             ui_class=cb.hint))
    return Div(head, *(bar(r) for r in bars))
