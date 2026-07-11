"""Theme-aware matplotlib chart canvas: donut, multi-line and stacked bars.

The figure paints an OPAQUE background in the card's surface colour (instead of
a transparent figure). That matches the card seamlessly in both light and dark
mode and avoids stray anti-aliased edge artefacts. Chart data is passed in
integer cents; the y-axis is formatted as compact euros. Colours come from the
active theme palette and can be swapped at runtime via :meth:`set_colors`, so a
theme toggle does not require rebuilding the whole view.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")  # bind to the Qt6 Agg backend before importing canvas

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402


def _euro_short(cents: int) -> str:
    """Compact euro label for an axis tick (e.g. '1.250 €', '12,5k €')."""
    euros = cents / 100.0
    sign = "-" if euros < 0 else ""
    a = abs(euros)
    if a >= 10_000:
        return f"{sign}{a / 1000:.0f}k €".replace(".", ",")
    if a >= 1_000:
        return f"{sign}{a / 1000:.1f}k €".replace(".", ",")
    return f"{sign}{a:.0f} €"


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self, colors: dict, width: float = 4.4, height: float = 3.0) -> None:
        self.fig = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.fig)
        self.colors = colors
        # Drilldown wiring (v3.2): the views may register a click callback per
        # chart type; the single mpl handler below dispatches to whichever one
        # the current chart set. Connected once per canvas instance.
        self._on_slice = None            # donut: called with the slice label
        self._on_month = None            # line/bars: called with the x index
        self._donut_wedges: list = []    # [(wedge, label)] of the current donut
        self._month_count = 0            # x range of the current line/bar chart
        self.mpl_connect("button_press_event", self._on_click)

    def _on_click(self, event) -> None:
        if event.button != 1:
            return
        if self._on_slice and self._donut_wedges:
            for wedge, label in self._donut_wedges:
                if wedge.contains_point((event.x, event.y)):
                    self._on_slice(label)
                    return
        if self._on_month and self._month_count and event.xdata is not None \
                and event.inaxes is not None:
            index = round(event.xdata)
            if 0 <= index < self._month_count and abs(event.xdata - index) <= 0.5:
                self._on_month(index)

    def set_colors(self, colors: dict) -> None:
        """Swap the palette (caller redraws), so theme toggles need no rebuild."""
        self.colors = colors

    def _bg(self) -> str:
        return self.colors["surface"]

    def _no_data(self, ax) -> None:
        ax.text(0.5, 0.5, "Keine Daten", ha="center", va="center",
                color=self.colors["text_faint"], fontsize=10, transform=ax.transAxes)
        ax.axis("off")
        self.draw()

    def _reset_click_targets(self) -> None:
        self._on_slice = None
        self._on_month = None
        self._donut_wedges = []
        self._month_count = 0

    # -- donut (categorical share) -----------------------------------------
    def donut(self, labels: list[str], values: list[float], slice_colors: list[str],
              center_text: str = "", on_slice=None) -> None:
        self.fig.clear()
        self._reset_click_targets()
        self.fig.patch.set_facecolor(self._bg())
        ax = self.fig.add_axes((0.0, 0.0, 1.0, 1.0))
        ax.set_facecolor(self._bg())
        ax.axis("off")
        ax.set_aspect("equal")
        if not values or sum(values) <= 0:
            self._no_data(ax)
            return
        ax.set_xlim(-1.6, 1.6)
        ax.set_ylim(-1.18, 1.18)
        wedges, _ = ax.pie(
            values, colors=slice_colors, startangle=90, counterclock=False,
            radius=1.0, center=(0.0, 0.0),
            wedgeprops=dict(width=0.42, edgecolor=self._bg(), linewidth=2),
        )
        if on_slice is not None:
            self._on_slice = on_slice
            self._donut_wedges = list(zip(wedges, labels))
        if center_text:
            ax.text(0, 0, center_text, ha="center", va="center",
                    color=self.colors["text"], fontsize=13, fontweight="bold")
        self.draw()

    # -- shared axis styling -----------------------------------------------
    def _style_axes(self, ax, labels: list[str]) -> None:
        c = self.colors
        self.fig.patch.set_facecolor(self._bg())
        ax.set_facecolor(self._bg())
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(c["border"])
        ax.tick_params(colors=c["text_muted"], labelsize=8, length=0)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: _euro_short(int(v))))
        ax.grid(axis="y", color=c["border"], linewidth=0.8, alpha=0.7)
        ax.set_axisbelow(True)
        n = len(labels)
        ax.set_xticks(range(n))
        rotation = 0 if n <= 8 else (30 if n <= 14 else 45)
        ax.set_xticklabels(labels, rotation=rotation,
                           ha="center" if rotation == 0 else "right")

    # -- balance history + dashed forecast continuation ---------------------
    def saldo_forecast(self, labels: list[str], actual_cents: list[int],
                       forecast_cents: list[int], color: str,
                       event_indices: list[int] | None = None) -> None:
        """One continuous balance line: solid actual months, dashed projection.

        ``labels`` covers actual + forecast months in order; the forecast
        segment starts right after the last actual month and is connected to
        it. A vertical "Heute" separator marks the boundary; ``event_indices``
        (absolute positions within ``labels``) get a dot marker so drop-off
        months are visible directly in the line.
        """
        self.fig.clear()
        self._reset_click_targets()
        ax = self.fig.add_subplot(111)
        if not labels or not forecast_cents:
            ax.set_facecolor(self._bg())
            self._no_data(ax)
            return
        self._style_axes(ax, labels)
        c = self.colors
        n_actual = len(actual_cents)
        ys_actual = [v / 100.0 for v in actual_cents]
        ys_forecast = [v / 100.0 for v in forecast_cents]
        if ys_actual:
            ax.plot(range(n_actual), ys_actual, color=color, linewidth=2.2,
                    marker="o", markersize=3.5, zorder=3)
            # Connect the segments: dashed line starts at the last actual point.
            xs_f = list(range(n_actual - 1, n_actual + len(ys_forecast)))
            ys_f = [ys_actual[-1]] + ys_forecast
        else:
            xs_f = list(range(len(ys_forecast)))
            ys_f = ys_forecast
        ax.plot(xs_f, ys_f, color=color, linewidth=2.2, linestyle=(0, (5, 4)),
                marker="o", markersize=3.0, markerfacecolor=self._bg(), zorder=3)
        if ys_actual:
            boundary = n_actual - 1
            ax.axvline(boundary, color=c["text_faint"], linewidth=1.0,
                       linestyle=(0, (2, 3)))
            ax.text(boundary, 1.02, "Heute", ha="center", va="bottom",
                    color=c["text_faint"], fontsize=8,
                    transform=ax.get_xaxis_transform())
        for idx in (event_indices or []):
            if 0 <= idx < len(labels):
                y = (ys_actual + ys_forecast)[idx]
                ax.plot([idx], [y], marker="o", markersize=7.5,
                        markerfacecolor=c["amber"], markeredgecolor=self._bg(),
                        markeredgewidth=1.5, zorder=4)
        ax.axhline(0, color=c["border"], linewidth=1.0)
        self.fig.subplots_adjust(left=0.13, right=0.98, top=0.9, bottom=0.2)
        self.draw()

    # -- multi-line trend ---------------------------------------------------
    def line_series(self, labels: list[str], series: list[tuple],
                    on_month=None) -> None:
        """``series`` = list of (name, values_cents, colour) drawn as lines.

        ``on_month`` (optional) is called with the clicked month index.
        """
        self.fig.clear()
        self._reset_click_targets()
        ax = self.fig.add_subplot(111)
        if not labels or not series:
            ax.set_facecolor(self._bg())
            self._no_data(ax)
            return
        if on_month is not None:
            self._on_month = on_month
            self._month_count = len(labels)
        self._style_axes(ax, labels)
        xs = list(range(len(labels)))
        for name, values, color in series:
            ys = [v / 100.0 for v in values]
            ax.plot(xs, ys, color=color, linewidth=2.2, marker="o", markersize=3.5,
                    label=name, zorder=3)
        ax.axhline(0, color=self.colors["border"], linewidth=1.0)
        # No in-chart legend: the view renders a richer colour legend with sums
        # beneath the canvas (and it never overlaps the data).
        self.fig.subplots_adjust(left=0.13, right=0.98, top=0.96, bottom=0.2)
        self.draw()

    # -- stacked category bars ---------------------------------------------
    def bars_stacked(self, labels: list[str], series: list[tuple],
                     on_month=None) -> None:
        """``series`` = list of (name, values_cents, colour) stacked per month.

        ``on_month`` (optional) is called with the clicked month index.
        """
        self.fig.clear()
        self._reset_click_targets()
        ax = self.fig.add_subplot(111)
        total = sum(sum(v for v in values) for _n, values, _c in series) if series else 0
        if not labels or not series or total <= 0:
            ax.set_facecolor(self._bg())
            self._no_data(ax)
            return
        if on_month is not None:
            self._on_month = on_month
            self._month_count = len(labels)
        self._style_axes(ax, labels)
        xs = list(range(len(labels)))
        bottoms = [0.0] * len(labels)
        for name, values, color in series:
            ys = [v / 100.0 for v in values]
            ax.bar(xs, ys, bottom=bottoms, color=color, width=0.62, label=name, zorder=3)
            bottoms = [b + y for b, y in zip(bottoms, ys)]
        # Legend is rendered by the view beneath the canvas (category + colour),
        # so nothing overlaps the stacked bars.
        self.fig.subplots_adjust(left=0.13, right=0.98, top=0.96, bottom=0.2)
        self.draw()
