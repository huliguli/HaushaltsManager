"""Theme-aware matplotlib donut chart canvas.

The figure paints an OPAQUE background in the card's surface colour (instead of
a transparent figure). That matches the card seamlessly in both light and dark
mode and avoids the stray anti-aliased edge artefacts a transparent Agg canvas
produced on the right side of the donut. Values are passed in euros (floats).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")  # bind to the Qt6 Agg backend before importing canvas

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self, colors: dict, width: float = 4.4, height: float = 3.0) -> None:
        self.fig = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.fig)
        self.colors = colors

    def _bg(self) -> str:
        return self.colors["surface"]

    def _no_data(self, ax) -> None:
        ax.text(0.5, 0.5, "Keine Daten", ha="center", va="center",
                color=self.colors["text_faint"], fontsize=10, transform=ax.transAxes)
        ax.axis("off")
        self.draw()

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
