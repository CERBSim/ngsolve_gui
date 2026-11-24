from ngapp.components import *

from .view.core.widgets import on_cls

from .cerbsim_style import (
    nav_panel,
    panel_header,
    panel_header_title,
    panel_scroll,
    nav_search,
    nav_group_row,
    nav_group_caret,
    nav_group_caret_collapsed,
    nav_group_name,
    nav_count_badge,
    nav_item,
    nav_item_active,
    nav_number_hint,
    nav_side,
    avatar_min,
    grow,
)

_TYPE_GROUPS = {
    "geometry": ("Geometries", "mdi-cube"),
    "mesh": ("Meshes", "mdi-vector-triangle"),
    "function": ("Functions", "mdi-function-variant"),
    "plot": ("Plots", "mdi-chart-line"),
}


class Navigator(Div):
    def __init__(self, app_data, on_load_file=None, explorer=None):
        """``explorer(query)`` builds the object list below the tabs."""
        self.app_data = app_data
        self._query = Observable("", "nav_query", converter=lambda v: (v or "").strip().lower())
        self._collapsed = Observable(frozenset(), "nav_collapsed")
        # tab names in display order, unfiltered: the 1-9 shortcuts stay stable
        self._order = computed(
            lambda: [t["name"] for _l, _i, tabs in self._by_type() for t in tabs])

        load_btn = QBtn(
            QTooltip("Load file  ·  geometry / mesh / .py"),
            ui_flat=True, ui_dense=True, ui_round=True, ui_size="sm",
            ui_icon="mdi-plus", ui_color="grey-7",
        )
        if on_load_file is not None:
            load_btn.on_click(lambda *a: on_load_file())

        header = Div(
            Div("Navigator", ui_class=panel_header_title),
            load_btn,
            ui_class=panel_header,
        )

        search = QInput(
            ui_model_value=self._query,
            ui_dense=True,
            ui_borderless=True,
            ui_clearable=True,
            ui_debounce=150,
            ui_label="Filter objects…",
            ui_class=str(grow),
        )
        search_box = Div(
            QIcon(ui_name="mdi-magnify", ui_size="16px"),
            search,
            ui_class=nav_search,
        )

        scroll = Div(
            For(computed(self._groups), self._group, key=lambda g: g[0], reactive=True),
            *([explorer(self._query)] if explorer is not None else []),
            Div(ui_style="height: 12px;"),
            ui_class=panel_scroll,
        )
        super().__init__(header, search_box, scroll, ui_class=nav_panel)

    def select_by_index(self, n):
        """Select the nth item (1-based). Returns True if valid."""
        order = self._order.value
        if 1 <= n <= min(9, len(order)):
            self.app_data.select(order[n - 1])
            return True
        return False

    def _by_type(self):
        """[(label, icon, [record, ...]), ...] in canonical order."""
        groups = {}
        for tab in self.app_data.tabs.value:
            groups.setdefault(tab.get("type", "unknown"), []).append(tab)
        out = [(label, icon, groups[key]) for key, (label, icon) in _TYPE_GROUPS.items()
               if groups.get(key)]
        out += [(key.title(), "mdi-help", tabs) for key, tabs in groups.items()
                if key not in _TYPE_GROUPS]
        return out

    def _groups(self):
        """(label, icon, count, matching records) of the groups to show."""
        q = self._query.value
        out = []
        for label, icon, tabs in self._by_type():
            matches = tuple(t for t in tabs if not q or q in t["title"].lower())
            if matches or not q:
                out.append((label, icon, len(tabs), matches))
        return out

    def _group(self, group):
        label, icon = group.peek()[:2]
        collapsed = computed(lambda: label in self._collapsed.value)
        caret = QIcon(ui_name="mdi-chevron-down", ui_size="16px", ui_class=on_cls(
            nav_group_caret, nav_group_caret_collapsed, collapsed))
        row = Div(
            caret,
            QIcon(ui_name=icon, ui_size="15px"),
            Div(label, ui_class=nav_group_name),
            Div(computed(lambda: str(group.value[2])), ui_class=nav_count_badge),
            ui_class=nav_group_row,
        )
        row.on("click", lambda e=None: setattr(
            self._collapsed, "value", self._collapsed.value ^ {label}))
        items = computed(lambda: () if collapsed.value else group.value[3])
        return [row, For(items, lambda t: self._item(t, icon), key=lambda t: t["uid"],
                         reactive=True)]

    def _item(self, tab, group_icon):
        name = tab.peek()["name"]
        active = computed(lambda: self.app_data.active.value == name)

        def number():
            order = self._order.value
            i = order.index(name) + 1 if name in order else 0
            return str(i) if 0 < i <= 9 else ""

        icon = QIcon(
            ui_name=computed(lambda: tab.value.get("icon", group_icon)),
            ui_size="xs",
            ui_color=computed(lambda: "primary" if active.value else "grey-7"),
        )
        item = QItem(
            QItemSection(Div(computed(number), ui_class=nav_number_hint),
                         ui_side=True, ui_class=nav_side),
            QItemSection(icon, ui_avatar=True, ui_class=avatar_min),
            QItemSection(Div(computed(lambda: tab.value["title"]))),
            self._context_menu(name, tab),
            ui_clickable=True,
            ui_active=active,
            ui_active_class=str(nav_item_active),
            ui_dense=True,
            ui_class=nav_item,
        )
        item.on_click(lambda e=None: self.app_data.select(name))
        item.on("mousedown", lambda e: e.value.get("button") == 1
                and self.app_data.delete_tab(name))
        return item

    def _context_menu(self, name, tab):
        delete_item = QItem(
            QItemSection(
                QIcon(ui_name="mdi-delete", ui_size="xs"),
                ui_avatar=True,
                ui_class=avatar_min,
            ),
            QItemSection("Delete"),
            ui_clickable=True,
            ui_dense=True,
        )
        delete_item.on_click(lambda e=None: self.app_data.delete_tab(name))

        title = Observable("", "rename_title")
        open_ = Observable(False, "rename_open")
        rename_btn = QBtn(ui_label="OK", ui_color="primary", ui_flat=True, ui_dense=True)
        rename_dialog = QDialog(
            QCard(
                QCardSection("Rename"),
                QCardSection(QInput(ui_model_value=title, ui_dense=True, ui_autofocus=True)),
                QCardActions(rename_btn, ui_align="right"),
            ),
            ui_model_value=open_,
        )

        def rename(e=None):
            if (title.value or "").strip():
                self.app_data.rename_tab(name, title.value.strip())
            open_.value = False

        def start_rename(e=None):
            title.value = tab.value["title"]
            open_.value = True

        rename_btn.on_click(rename)
        rename_item = QItem(
            QItemSection(
                QIcon(ui_name="mdi-pencil", ui_size="xs"),
                ui_avatar=True,
                ui_class=avatar_min,
            ),
            QItemSection("Rename"),
            rename_dialog,
            ui_clickable=True,
            ui_dense=True,
        )
        rename_item.on_click(start_rename)

        return QMenu(
            QList(rename_item, delete_item, ui_dense=True),
            ui_context_menu=True,
        )
