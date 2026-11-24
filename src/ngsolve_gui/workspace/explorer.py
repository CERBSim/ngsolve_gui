"""Object explorer: the workspace entries, listed in the navigator."""

from ngapp.components import *

from .. import cerbsim_style as cb
from ..view.core.widgets import on_cls

_CHIP = ("display: inline-block; padding: 0 6px; margin: 2px 4px 0 0; cursor: default;"
         " border-radius: var(--r-pill); font-size: 11px; border: 1px solid var(--border);")


class Explorer(Div):
    """``on_draw(name, mesh=None, title=None)`` opens a view of an object (on
    the mesh or region ``mesh``), ``on_highlight(name, region)`` highlights a region
    of a mesh in the current view (None clears). Folded, the workspace is
    not scanned."""

    def __init__(self, workspace, query, on_draw, on_highlight):
        self._on_draw, self._on_highlight = on_draw, on_highlight
        self._open = Observable(None, "explorer_open")
        self._entries = workspace.entries
        shown = workspace.shown
        collapsed = computed(lambda: not shown.value)
        matches = computed(lambda: tuple(
            e for e in workspace.entries.value if not query.value or query.value in e.name.lower()))

        refresh = QBtn(QTooltip("Rescan the script variables"), ui_flat=True, ui_dense=True,
                       ui_round=True, ui_size="xs", ui_icon="mdi-refresh", ui_color="grey-7")
        refresh.on_click(lambda *a: workspace.refresh())
        toggle = Div(
            QIcon(ui_name="mdi-chevron-down", ui_size="16px", ui_class=on_cls(
                cb.nav_group_caret, cb.nav_group_caret_collapsed, collapsed)),
            QIcon(ui_name="mdi-code-braces", ui_size="15px"),
            Div("Workspace", ui_class=cb.nav_group_name),
            Show(shown, lambda: Div(computed(lambda: str(len(workspace.entries.value))),
                                    ui_class=cb.nav_count_badge)),
            ui_class="row items-center no-wrap " + str(cb.grow), ui_style="gap: 7px;",
        )
        toggle.on("click", lambda e=None: shown.toggle())
        items = computed(lambda: () if collapsed.value else matches.value)
        super().__init__(
            Div(toggle, refresh, ui_class=cb.nav_group_row),
            Show(computed(lambda: not collapsed.value and not matches.value),
                 lambda: Div("No objects. Variables of a loaded script appear here.",
                             ui_class=cb.nav_empty)),
            For(items, self._item, key=lambda e: e.name, reactive=True),
        )

    def _item(self, entry):
        name = entry.peek().name
        head = Div(
            QIcon(ui_name=computed(lambda: entry.value.icon), ui_size="xs", ui_color="grey-7"),
            Div(name, ui_class="ellipsis " + str(cb.grow)),
            Div(computed(lambda: entry.value.kind), ui_class=cb.hint, ui_style="font-size: 11px;"),
            ui_class="row items-center no-wrap " + str(cb.gap_sm), ui_style="cursor: pointer;",
        )
        head.on("click", lambda e=None: setattr(
            self._open, "value", None if self._open.value == name else name))
        return Div(head, Show(computed(lambda: self._open.value == name),
                              lambda: self._details(entry, name)), ui_class=cb.nav_item)

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
            fits = [e.name for e in entries if e.target
                    and (fn.mesh_id is None or e.mesh_id == fn.mesh_id)]
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

        return Div(
            For(computed(lambda: entry.value.details), row),
            regions("material", "Materials"),
            regions("boundary", "Boundaries"),
            Show(computed(lambda: entry.value.on_mesh and bool(options.value)), lambda: draw_on,
                 otherwise=lambda: Show(computed(lambda: entry.value.drawable), lambda: btn(
                     "Draw", "Open a view", lambda: self._on_draw(name)))),
            ui_style="padding: 4px 0 4px 22px; font-size: 12px;",
        )
