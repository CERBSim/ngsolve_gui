"""Reusable property-panel widgets in the designer's visual language.

These are plain ngapp components (Div-based) so they bind directly to the
component's Observables and update the WebGPU scene the same way the old Quasar
checkboxes did — they are drop-in replacements with the designer look.
"""

from ngapp.components import *

from . import cerbsim_style as cb


def on_cls(base, on, observable):
    """Class string bound to a boolean observable: ``base`` plus ``on`` while true."""
    return computed(lambda: f"{base} {on}" if observable.value else str(base))


class Section(Div):
    """Collapsible property section: banded header + colored icon box + body.

    Two modes:
      * normal     — a caret toggles the body open/closed.
      * switchable — a header switch reflects an Observable; the body (details)
                     is shown only while the feature is on, and the icon box is
                     muted while off.

    ``self.open`` is the observable of the open state (the feature observable
    for switchable sections). Subclasses set a ``section_key`` class attribute
    (used for the icon-box accent color and for exclude-by-key filtering).
    """

    section_key = "display"

    def __init__(self, *body, icon, title, opened=False,
                 switchable=False, observable=None, info=None, head_actions=None):
        if switchable and observable is not None:
            self.open = observable
        else:
            switchable = False
            self.open = Observable(bool(opened), "open")
        is_open = computed(lambda: bool(self.open.value))

        ico = Div(QIcon(ui_name=icon), ui_class=cb.psec_ico, ui_style=computed(
            lambda: cb.sico_style(self.section_key, muted=switchable and not is_open.value)))
        main = []
        if not switchable:
            main.append(Div(QIcon(ui_name="mdi-chevron-down"), ui_class=cb.psec_caret))
        main.append(ico)
        main.append(Div(title, ui_class=cb.psec_title))
        if info:
            main.append(Div(
                QIcon(ui_name="mdi-information-outline"), QTooltip(info),
                ui_class=cb.htip,
            ))
        if switchable:
            main.append(Div(ui_class=on_cls(cb.prop_switch, cb.prop_switch_on, is_open)))

        # Only the main area toggles the section; header actions handle their own
        # clicks (and live to the right of the title).
        head_main = Div(*main, ui_class=cb.psec_head_main)
        head_main.on("click", lambda e=None: self.open.toggle())
        head_children = [head_main]
        head_style = None
        if head_actions:
            head_children.append(Div(*head_actions, ui_class=cb.psec_head_actions))
            # In a narrow panel the actions wrap below the title instead of
            # covering it.
            head_main.ui_style = "min-width: max-content; min-height: 28px;"
            head_style = ("flex-wrap: wrap; height: auto; min-height: 40px; "
                          "padding-top: 6px; padding-bottom: 6px; row-gap: 6px;")
        suffix = " cb-switchable" if switchable else ""
        head = Div(*head_children, ui_style=head_style, ui_class=computed(
            lambda: f"{cb.psec_head} {'cb-open' if is_open.value else 'cb-collapsed'}{suffix}"))
        self._body = Div(*body, ui_class=cb.psec_body)
        self._body.ui_hidden = computed(lambda: not is_open.value)

        super().__init__(head, self._body, ui_class=cb.psec)


class Chip(Div):
    """Toggleable option chip (icon + label) bound to an Observable."""

    def __init__(self, label, icon=None, observable=None, small=False):
        children = []
        if icon:
            children.append(QIcon(ui_name=icon))
        children.append(label)
        base = str(cb.opt_chip) + (" " + str(cb.opt_chip_sm) if small else "")
        super().__init__(*children, ui_class=on_cls(base, cb.opt_chip_on, observable))
        self.on("click", lambda e=None: observable.toggle())


def chip_row(*chips):
    """Wrap chips in the flex-wrap chip container."""
    return Div(*chips, ui_class=cb.opt_chips)


class Toggle(Div):
    """A label with a switch on the right, bound to an Observable."""

    def __init__(self, label, observable):
        switch = Div(ui_class=on_cls(cb.prop_switch, cb.prop_switch_on, observable))
        super().__init__(Div(label), switch, ui_class=cb.prop_toggle)
        self.on("click", lambda e=None: observable.toggle())


class SubToggleBlock(Div):
    """A flow sub-feature inside the grouped flow card: a label+switch header
    whose settings body is shown only while the feature is enabled."""

    def __init__(self, label, observable, *body):
        body = Div(*body, ui_class=cb.flow_sub_body)
        body.ui_hidden = computed(lambda: not observable.value)
        super().__init__(Toggle(label, observable), body, ui_class=cb.flow_sub)


class PickPill(Div):
    """A small round pill (e.g. S / F / E / V) bound to an Observable."""

    def __init__(self, label, observable, tooltip=None):
        children = [label]
        if tooltip:
            children.append(QTooltip(tooltip))
        super().__init__(*children, ui_class=on_cls(cb.chk_pill, cb.chk_pill_on, observable))
        self.on("click", lambda e=None: observable.toggle())


def field(label, control):
    """Uppercase micro-label stacked above a control."""
    return Div(Div(label, ui_class=cb.prop_flab), control, ui_class=cb.prop_field)


class ColorbarLegend(Div):
    """In-viewport colorbar legend (top-right corner). Shows the quantity, a
    vertical gradient and ticks; clicking it opens a popover to pick the
    colormap, edit min/max, toggle autoscale, and (vectors) choose the shown
    component."""

    CMAPS = ["rainbow", "turbo", "viridis", "plasma", "cet_l20",
             "matlab:jet", "matplotlib:coolwarm"]

    def __init__(self, colormap, field_part, title):
        mn, mx = colormap.min, colormap.max
        auto = colormap.autoscale

        title = [Div(computed(title), ui_class=cb.legend_quantity)]
        selector = self._component_selector(field_part)
        if selector is not None:
            title.append(selector)

        # typing a range ends autoscale; the colormap follows the observables
        def end_autoscale(e=None):
            auto.value = False

        self.maxval = QInput(ui_type="number", ui_dense=True, ui_borderless=True,
                             ui_model_value=mx)
        self.minval = QInput(ui_type="number", ui_dense=True, ui_borderless=True,
                             ui_model_value=mn)
        self.maxval.on_update_model_value(end_autoscale)
        self.minval.on_update_model_value(end_autoscale)

        def tick(t):
            def text():
                a, b = mn.value, mx.value
                return self._fmt(a + t * (b - a), abs(b - a))
            return Div(computed(text))

        self._pop_open = Observable(False, "legend_pop")
        bar = Div(QTooltip("Colormap options"), ui_class=cb.legend_bar, ui_style=computed(
            lambda: "background: " + cb.colormap_gradient_vertical(colormap.name.value) + ";"))
        bar.on("click", lambda e=None: self._pop_open.toggle())
        ticks = Div(self.maxval, tick(0.75), tick(0.5), tick(0.25), self.minval,
                    ui_class=cb.legend_ticks)

        auto_pill = Div(
            QIcon(ui_name=computed(lambda: "mdi-lock" if auto.value else "mdi-lock-open-variant")),
            "Auto", ui_class=on_cls(cb.ps_auto, cb.ps_auto_on, auto))
        auto_pill.on("click", lambda e=None: auto.toggle())

        pop = self._build_pop(colormap)
        pop.ui_hidden = computed(lambda: not self._pop_open.value)

        super().__init__(
            Div(*title, ui_class=cb.legend_title),
            Div(bar, ticks, ui_class=cb.legend_wrap),
            Div(auto_pill, ui_class="row q-mt-sm"),
            pop,
            ui_class=cb.vp_legend,
        )

    def _build_pop(self, colormap):
        rows = [Div(Div("Colormap options", ui_class=cb.ps_lab),
                    _close_x(lambda: setattr(self._pop_open, "value", False)),
                    ui_class="row items-center justify-between")]

        name = colormap.name
        opt_rows = []
        for n in self.CMAPS:
            row = Div(
                Div(ui_class=cb.cmap_swatch, ui_style="background: " + cb.colormap_gradient(n) + ";"),
                Div(n, ui_class=cb.cmap_opt_name),
                QIcon(ui_name="mdi-check"),
                ui_class=on_cls(cb.cmap_opt, cb.cmap_opt_on, computed(lambda n=n: name.value == n)),
            )
            row.on("click", lambda e=None, n=n: setattr(name, "value", n))
            opt_rows.append(row)
        rows.append(field("Colormap", Div(*opt_rows)))

        ncolors = QInput(ui_type="number", ui_model_value=colormap.ncolors,
                         ui_dense=True, ui_filled=True, ui_class=cb.input_tiny)
        rows.append(Div(Chip("Discrete", "mdi-grid", colormap.discrete, small=True),
                        field("N colors", ncolors),
                        ui_class="row items-end " + str(cb.gap_sm)))
        return Div(*rows, ui_class=cb.legend_pop)

    def _component_selector(self, field_part):
        """|u| / component picker beside the legend title. Fields with up to 3
        components get a segmented control, wider ones a |u| pill and a
        dropdown (keeps the legend narrow)."""
        dim = field_part.dim
        if dim <= 1:
            return None
        names = field_part.labels
        shown = Observable("norm", "legend_component")
        shown.on_change(lambda v, _o: setattr(
            field_part.component, "value", -1 if v == "norm" else int(v)))
        if dim <= 3:
            opts = [("norm", "|u|")] + [(str(i), names[i]) for i in range(dim)]
            return Div(Segmented(opts, shown), ui_class=cb.legend_comp)
        norm = Div("|u|", ui_class=on_cls(cb.legend_pill, cb.seg_btn_on,
                                          computed(lambda: shown.value == "norm")))
        norm.on("click", lambda e=None: setattr(shown, "value", "norm"))
        select = QSelect(
            QTooltip("Component"),
            ui_options=[{"label": n, "value": i} for i, n in enumerate(names)],
            ui_model_value=computed(lambda: None if shown.value == "norm" else int(shown.value)),
            ui_emit_value=True, ui_map_options=True,
            ui_dense=True, ui_borderless=True,
            ui_class=cb.legend_comp_select,
        )
        select.on_update_model_value(lambda e: setattr(shown, "value", str(e.value)))
        return Div(norm, select, ui_class=cb.legend_comp)

    @staticmethod
    def _fmt(v, span=0.0):
        # values far below the resolution of the bar are 0 (e.g. 1e-8 next to 1)
        if abs(v) < 1e-4 * span:
            v = 0.0
        return f"{v:.3g}"


def _close_x(callback):
    x = Div(QIcon(ui_name="mdi-close"), ui_class=cb.probe_del)
    x.on("click", lambda e=None: callback())
    return x


class MoreDisclosure(Div):
    """Inline 'More options' / 'Fewer options' disclosure that shows extra body."""

    def __init__(self, *body, label_more="More options", label_less="Fewer options"):
        is_open = Observable(False, "more_open")
        toggle = Div(
            QIcon(ui_name="mdi-chevron-down"),
            Div(computed(lambda: label_less if is_open.value else label_more)),
            ui_class=computed(lambda: str(cb.psec_more) + ("" if is_open.value else " cb-collapsed")),
        )
        toggle.on("click", lambda e=None: is_open.toggle())
        body = Div(*body, ui_class=cb.psec_body + " q-pa-none",
                   ui_style="padding: 0; gap: 11px;")
        body.ui_hidden = computed(lambda: not is_open.value)
        super().__init__(body, toggle, ui_class="column " + str(cb.gap_sm))


class Segmented(Div):
    """A segmented button group. ``options`` is a list of (value, label);
    ``value`` is an Observable of the selected value (or the initial value).
    ``on_change(value)`` is called when the user selects a button."""

    def __init__(self, options, value, on_change=None):
        if not isinstance(value, Observable):
            value = Observable(value, "segmented")
        self.value = value

        def select(v):
            value.value = v
            if on_change:
                on_change(v)

        children = []
        for val, lab in options:
            b = Div(lab, ui_class=on_cls(cb.seg_btn, cb.seg_btn_on,
                                         computed(lambda val=val: value.value == val)))
            b.on("click", lambda e=None, v=val: select(v))
            children.append(b)
        super().__init__(*children, ui_class=cb.seg)
