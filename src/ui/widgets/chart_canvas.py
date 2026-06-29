"""Theme-aware matplotlib chart canvas (donut, bars, line).

The figure paints an OPAQUE background in the card's surface colour (instead of
a transparent figure). That matches the card seamlessly in both light and dark
mode and avoids the stray anti-aliased edge artefacts a transparent Agg canvas
produced on the right side of the donut. Values are passed in euros (floats);
axis labels are formatted in German style.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")  # bind to the Qt6 Agg backend before importing canvas

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


def _euro(value: float) -> str:
    """Format a euro float as a compact German label (e.g. '1.234 €')."""
    s = f"{value:,.0f}".replace(",", ".")
    return f"{s} €"


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self, colors: dict, width: float = 4.4, height: float = 3.0) -> None:
        self.fig = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.fig)
        self.colors = colors

    def set_colors(self, colors: dict) -> None:
        self.colors = colors

    def _bg(self) -> str:
        return self.colors["surface"]

    def _no_data(self, ax) -> None:
        ax.text(0.5, 0.5, "Keine Daten", ha="center", va="center",
                color=self.colors["text_faint"], fontsize=10, transform=ax.transAxes)
        ax.axis("off")
        self.draw()

    def _reset(self):
        """Clear and return an axes with an opaque, theme-coloured background."""
        self.fig.clear()
        self.fig.patch.set_facecolor(self._bg())
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(self._bg())
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=self.colors["text_muted"], labelsize=8)
        return ax

    # -- chart types --------------------------------------------------------
    def donut(self, labels: list[str], values: list[float], slice_colors: list[str],
              center_text: str = "") -> None:
        self.fig.clear()
        self.fig.patch.set_facecolor(self._bg())
        # Axes fills the whole figure; explicit, wider-than-tall limits keep the
        # ring centred with even margins and nothing painted at the figure edges.
        ax = self.fig.add_axes((0.0, 0.0, 1.0, 1.0))
        ax.set_facecolor(self._bg())
        ax.axis("off")
        ax.set_aspect("equal")
        if not values or sum(values) <= 0:
            self._no_data(ax)
            return
        ax.set_xlim(-1.6, 1.6)
        ax.set_ylim(-1.18, 1.18)
        ax.pie(
            values, colors=slice_colors, startangle=90, counterclock=False,
            radius=1.0, center=(0.0, 0.0),
            wedgeprops=dict(width=0.42, edgecolor=self._bg(), linewidth=2),
        )
        if center_text:
            ax.text(0, 0, center_text, ha="center", va="center",
                    color=self.colors["text"], fontsize=13, fontweight="bold")
        self.draw()

    def vbars(self, labels: list[str], values: list[float], color: str) -> None:
        ax = self._reset()
        if not values:
            self._no_data(ax)
            return
        bars = ax.bar(range(len(values)), values, color=color, width=0.62, zorder=3)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=0)
        ax.set_yticks([])
        ax.grid(axis="y", color=self.colors["border"], linewidth=0.7, zorder=0)
        for rect, val in zip(bars, values):
            ax.annotate(_euro(val), xy=(rect.get_x() + rect.get_width() / 2, val),
                        xytext=(0, 3), textcoords="offset points", ha="center",
                        fontsize=8, color=self.colors["text_muted"])
        self.fig.subplots_adjust(left=0.04, right=0.98, top=0.90, bottom=0.16)
        self.draw()

    def line(self, labels: list[str], values: list[float], color: str) -> None:
        ax = self._reset()
        if not values:
            self._no_data(ax)
            return
        x = range(len(values))
        ax.plot(x, values, color=color, linewidth=2.2, marker="o", markersize=4, zorder=3)
        ax.fill_between(x, values, color=color, alpha=0.12, zorder=2)
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_yticks([])
        ax.grid(axis="y", color=self.colors["border"], linewidth=0.7, zorder=0)
        self.fig.subplots_adjust(left=0.04, right=0.98, top=0.94, bottom=0.16)
        self.draw()
