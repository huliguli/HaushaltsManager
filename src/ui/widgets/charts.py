"""Hand-drawn chart widgets (QPainter), replacing the matplotlib canvas in the UI.

Why not matplotlib: it brought its own typography, its own DPI handling and its
own idea of colour, which is a large part of why the app looked dated; it cost
~340 ms of import time on the startup path; and its axis labelling was wrong by
a factor of 100 because two layers each divided by 100 (see chart_canvas.py).

Design rules here: hairline grid, no frame, no chart junk, labels in the UI font
at UI sizes, and exactly ONE cents-to-euro conversion — at the label boundary.
Every widget takes integer CENTS, like the rest of the app.

matplotlib is still used by modules/file_handler/pdf_report.py, which is
deliberately Qt-free and tested without a QApplication.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from modules.money import format_eur, format_eur_short
from ui.theme import FONT_SIZES


def _nice_step(span: float, target_lines: int = 4) -> float:
    """A round grid step (1/2/2.5/5 x 10^n) near ``span / target_lines``."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target_lines)
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


class _Chart(QWidget):
    """Shared base: palette handling, opaque card-coloured background, fonts."""

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(parent)
        self.c = colors
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_colors(self, colors: dict) -> None:
        """Swap the palette; a theme toggle needs no rebuild."""
        self.c = colors
        self.update()

    def _begin(self) -> QPainter:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Paint the card colour rather than staying transparent: it keeps the
        # chart seamless inside a card and avoids stray anti-aliased edges.
        painter.fillRect(self.rect(), QColor(self.c["surface"]))
        return painter

    def _font(self, size_key: str = "small", weight: int = 400):
        from PyQt6.QtGui import QFont
        font = QFont(self.font())
        font.setPixelSize(FONT_SIZES[size_key])
        font.setWeight(QFont.Weight(weight))
        return font

    def _no_data(self, painter: QPainter, text: str = "Keine Daten") -> None:
        painter.setFont(self._font("small"))
        painter.setPen(QColor(self.c["text_faint"]))
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), text)


class Sparkline(_Chart):
    """A tiny trend line with a faint filled area — no axes, no labels."""

    def __init__(self, colors: dict, values: list[int] | None = None,
                 color_key: str = "primary", parent=None) -> None:
        super().__init__(colors, parent)
        self._values = list(values or [])
        self.color_key = color_key
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, values: list[int]) -> None:
        self._values = list(values)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = self._begin()
        values = self._values
        if len(values) < 2:
            painter.end()
            return
        width, height = self.width(), self.height()
        pad = 2.0
        low, high = min(values), max(values)
        flat = high == low
        span = (high - low) or 1

        points = []
        for index, value in enumerate(values):
            x = pad + (width - 2 * pad) * index / (len(values) - 1)
            # A constant series has no shape; centre it instead of gluing it to
            # the bottom edge, where it reads as "no data".
            fraction = 0.5 if flat else (value - low) / span
            points.append(QPointF(x, height - pad - (height - 2 * pad) * fraction))

        color = QColor(self.c[self.color_key])
        area = QPainterPath()
        area.moveTo(points[0].x(), height)
        for point in points:
            area.lineTo(point)
        area.lineTo(points[-1].x(), height)
        area.closeSubpath()
        fill = QColor(color)
        fill.setAlpha(30)
        painter.fillPath(area, fill)

        line = QPainterPath()
        line.moveTo(points[0])
        for point in points[1:]:
            line.lineTo(point)
        painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(line)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(points[-1], 2.4, 2.4)
        painter.end()


class _AxisChart(_Chart):
    """Base for charts with a month axis: grid, y labels, click-to-month."""

    month_clicked = pyqtSignal(int)

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(colors, parent)
        self.labels: list[str] = []
        self._plot = QRectF()
        self.setMinimumHeight(190)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.labels:
            return
        if not self._plot.contains(event.position()):
            return
        slot = self._plot.width() / len(self.labels)
        index = int((event.position().x() - self._plot.left()) / slot)
        if 0 <= index < len(self.labels):
            self.month_clicked.emit(index)

    def _axis(self, painter: QPainter, top_cents: float, bottom_cents: float = 0.0):
        """Draw grid + y labels; returns the plot rectangle."""
        painter.setFont(self._font("label"))
        metrics = painter.fontMetrics()
        widest = max(metrics.horizontalAdvance(format_eur_short(int(top_cents))), 34)
        left = widest + 10.0
        bottom = metrics.height() + 8.0
        self._plot = QRectF(left, 8.0, max(10.0, self.width() - left - 6.0),
                            max(10.0, self.height() - 8.0 - bottom))

        span_e = (top_cents - bottom_cents) / 100.0
        step_e = _nice_step(span_e, 4)
        painter.setPen(QColor(self.c["text_faint"]))
        value_e = math.floor(bottom_cents / 100.0 / step_e) * step_e
        while value_e <= span_e + bottom_cents / 100.0 + step_e * 0.01:
            cents = value_e * 100.0
            fraction = ((cents - bottom_cents) / (top_cents - bottom_cents)
                        if top_cents != bottom_cents else 0.0)
            y = self._plot.bottom() - self._plot.height() * fraction
            if self._plot.top() - 1 <= y <= self._plot.bottom() + 1:
                painter.setPen(QPen(QColor(self.c["border"]), 1))
                painter.drawLine(QPointF(self._plot.left(), y),
                                 QPointF(self._plot.right(), y))
                painter.setPen(QColor(self.c["text_faint"]))
                painter.drawText(
                    QRectF(0, y - metrics.height() / 2, left - 8, metrics.height()),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    format_eur_short(int(round(cents))))
            value_e += step_e
        return self._plot

    def _month_labels(self, painter: QPainter) -> None:
        if not self.labels:
            return
        painter.setFont(self._font("label"))
        metrics = painter.fontMetrics()
        slot = self._plot.width() / len(self.labels)
        # Only label every other month when they would otherwise collide —
        # rotating them 30 degrees (as matplotlib did) is harder to read.
        widest = max(metrics.horizontalAdvance(t) for t in self.labels)
        stride = 1 if widest + 6 <= slot else max(2, int((widest + 6) / slot) + 1)
        painter.setPen(QColor(self.c["text_faint"]))
        for index, text in enumerate(self.labels):
            if index % stride:
                continue
            painter.drawText(
                QRectF(self._plot.left() + slot * index, self._plot.bottom() + 4,
                       slot, metrics.height()),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), text)


class ColumnTrend(_AxisChart):
    """Income vs. spending as paired columns per month.

    Replaces the old three-line chart: two lines plus a balance line crossing
    each other were hard to read, and the balance is easier to judge from the
    gap between the pair.
    """

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(colors, parent)
        self.income: list[int] = []
        self.spending: list[int] = []

    def set_data(self, labels: list[str], income: list[int],
                 spending: list[int]) -> None:
        self.labels, self.income, self.spending = labels, income, spending
        self.update()

    def paintEvent(self, _event) -> None:
        painter = self._begin()
        if not self.labels or not (self.income or self.spending):
            self._no_data(painter)
            painter.end()
            return
        top = max(max(self.income, default=0), max(self.spending, default=0), 1)
        step = _nice_step(top / 100.0, 4) * 100.0
        top_cents = (math.floor(top / step) + 1) * step
        plot = self._axis(painter, top_cents)

        slot = plot.width() / len(self.labels)
        bar_w = min(13.0, slot * 0.30)
        gap = 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(len(self.labels)):
            centre = plot.left() + slot * (index + 0.5)
            pairs = ((self.income[index] if index < len(self.income) else 0,
                      self.c["green"], -(bar_w + gap) / 2),
                     (self.spending[index] if index < len(self.spending) else 0,
                      self.c["red"], (bar_w + gap) / 2))
            for value, key, offset in pairs:
                height = plot.height() * max(0, value) / top_cents
                painter.setBrush(QColor(key))
                painter.drawRoundedRect(
                    QRectF(centre + offset - bar_w / 2, plot.bottom() - height,
                           bar_w, height), 2, 2)

        painter.setPen(QPen(QColor(self.c["border"]), 1))
        painter.drawLine(QPointF(plot.left(), plot.bottom()),
                         QPointF(plot.right(), plot.bottom()))
        self._month_labels(painter)
        painter.end()


class BalanceLine(_AxisChart):
    """Balance over time: solid for actual months, dashed for the projection."""

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(colors, parent)
        self.actual: list[int] = []
        self.forecast: list[int] = []
        self.events: list[int] = []

    def set_data(self, labels: list[str], actual: list[int],
                 forecast: list[int], events: list[int] | None = None) -> None:
        self.labels, self.actual, self.forecast = labels, actual, forecast
        self.events = list(events or [])
        self.update()

    def paintEvent(self, _event) -> None:
        painter = self._begin()
        series = list(self.actual) + list(self.forecast)
        if not self.labels or not series:
            self._no_data(painter)
            painter.end()
            return

        high, low = max(series), min(series)
        pad = max(abs(high), abs(low), 100) * 0.12
        top_cents = high + pad
        bottom_cents = min(0, low - pad)
        plot = self._axis(painter, top_cents, bottom_cents)

        def point(index: int, value: int) -> QPointF:
            slot = plot.width() / max(1, len(self.labels) - 1)
            fraction = (value - bottom_cents) / (top_cents - bottom_cents)
            return QPointF(plot.left() + slot * index,
                           plot.bottom() - plot.height() * fraction)

        # Zero line: the most important reference in a balance chart.
        if bottom_cents < 0 < top_cents:
            zero_y = point(0, 0).y()
            painter.setPen(QPen(QColor(self.c["border_strong"]), 1))
            painter.drawLine(QPointF(plot.left(), zero_y), QPointF(plot.right(), zero_y))

        color = QColor(self.c["primary"])
        if self.actual:
            path = QPainterPath(point(0, self.actual[0]))
            for index, value in enumerate(self.actual[1:], start=1):
                path.lineTo(point(index, value))
            painter.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)

        if self.forecast:
            start = len(self.actual) - 1 if self.actual else 0
            path = QPainterPath(point(start, self.actual[-1] if self.actual
                                      else self.forecast[0]))
            for offset, value in enumerate(self.forecast, start=1):
                path.lineTo(point(start + offset, value))
            painter.setPen(QPen(color, 2.0, Qt.PenStyle.DashLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            if self.actual:
                boundary = point(start, self.actual[-1]).x()
                painter.setPen(QPen(QColor(self.c["text_faint"]), 1, Qt.PenStyle.DotLine))
                painter.drawLine(QPointF(boundary, plot.top()),
                                 QPointF(boundary, plot.bottom()))
                painter.setFont(self._font("label"))
                painter.setPen(QColor(self.c["text_faint"]))
                painter.drawText(QRectF(boundary - 30, plot.top() - 2, 60, 14),
                                 int(Qt.AlignmentFlag.AlignCenter), "Heute")

        painter.setPen(Qt.PenStyle.NoPen)
        for index in self.events:
            if 0 <= index < len(series):
                painter.setBrush(QColor(self.c["amber"]))
                painter.drawEllipse(point(index, series[index]), 4.0, 4.0)

        self._month_labels(painter)
        painter.end()


class CategoryBars(_Chart):
    """Ranked category list: name, bar, amount, share — and an optional budget tick.

    Replaces the donut. A donut with 14 slices (several under 2 %) is confetti
    and needs a legend as long as the chart; a sorted bar list is readable at a
    glance, needs no colour legend at all, and survives any number of categories.
    """

    category_clicked = pyqtSignal(str)

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(colors, parent)
        self.rows: list[tuple] = []          # (name, cents, limit_cents|None)
        self._row_height = 30
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_rows(self, rows: list[tuple]) -> None:
        self.rows = list(rows)
        self.setMinimumHeight(max(40, len(self.rows) * self._row_height + 4))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(360, max(40, len(self.rows) * self._row_height + 4))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.rows:
            return
        index = int(event.position().y() // self._row_height)
        if 0 <= index < len(self.rows):
            self.category_clicked.emit(self.rows[index][0])

    def paintEvent(self, _event) -> None:
        painter = self._begin()
        if not self.rows:
            self._no_data(painter)
            painter.end()
            return

        total = sum(row[1] for row in self.rows) or 1
        biggest = max(row[1] for row in self.rows) or 1
        font_name = self._font("table")
        font_value = self._font("table", weight=500)
        painter.setFont(font_name)
        metrics = painter.fontMetrics()

        name_w = min(200.0, max(120.0, self.width() * 0.30))
        value_w = 92.0
        share_w = 40.0
        bar_x = name_w + 10
        bar_w = max(30.0, self.width() - name_w - value_w - share_w - 26)

        for index, (name, cents, limit) in enumerate(self.rows):
            y = index * self._row_height
            middle = y + self._row_height / 2

            painter.setFont(font_name)
            painter.setPen(QColor(self.c["text"]))
            painter.drawText(
                QRectF(0, y, name_w, self._row_height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(name_w)))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.c["surface_3"]))
            painter.drawRoundedRect(QRectF(bar_x, middle - 4, bar_w, 8), 4, 4)

            over = limit is not None and limit > 0 and cents > limit
            painter.setBrush(QColor(self.c["red"] if over else self.c["primary"]))
            painter.drawRoundedRect(
                QRectF(bar_x, middle - 4, max(3.0, bar_w * cents / biggest), 8), 4, 4)

            if limit:
                tick_x = bar_x + bar_w * min(1.0, limit / biggest)
                painter.setPen(QPen(QColor(self.c["text_muted"]), 1.4))
                painter.drawLine(QPointF(tick_x, middle - 8), QPointF(tick_x, middle + 8))

            painter.setFont(font_value)
            painter.setPen(QColor(self.c["red"] if over else self.c["text"]))
            painter.drawText(
                QRectF(bar_x + bar_w + 8, y, value_w, self._row_height),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                format_eur(cents))
            painter.setPen(QColor(self.c["text_faint"]))
            painter.drawText(
                QRectF(bar_x + bar_w + 8 + value_w, y, share_w, self._row_height),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{round(100 * cents / total)} %")
        painter.end()


class StackedMonths(_AxisChart):
    """Stacked category columns per month (the trend view's breakdown)."""

    def __init__(self, colors: dict, parent=None) -> None:
        super().__init__(colors, parent)
        self.series: list[tuple] = []        # (name, values_cents, colour)

    def set_data(self, labels: list[str], series: list[tuple]) -> None:
        self.labels, self.series = labels, series
        self.update()

    def paintEvent(self, _event) -> None:
        painter = self._begin()
        totals = [sum(values[i] if i < len(values) else 0
                      for _n, values, _c in self.series)
                  for i in range(len(self.labels))]
        if not self.labels or not self.series or not any(totals):
            self._no_data(painter)
            painter.end()
            return

        top = max(totals) or 1
        step = _nice_step(top / 100.0, 4) * 100.0
        top_cents = (math.floor(top / step) + 1) * step
        plot = self._axis(painter, top_cents)

        slot = plot.width() / len(self.labels)
        bar_w = min(26.0, slot * 0.62)
        bottoms = [0.0] * len(self.labels)
        painter.setPen(Qt.PenStyle.NoPen)
        for _name, values, colour in self.series:
            painter.setBrush(QColor(colour))
            for index in range(len(self.labels)):
                value = values[index] if index < len(values) else 0
                if value <= 0:
                    continue
                height = plot.height() * value / top_cents
                y = plot.bottom() - bottoms[index] - height
                painter.drawRect(QRectF(plot.left() + slot * (index + 0.5) - bar_w / 2,
                                        y, bar_w, height))
                bottoms[index] += height

        painter.setPen(QPen(QColor(self.c["border"]), 1))
        painter.drawLine(QPointF(plot.left(), plot.bottom()),
                         QPointF(plot.right(), plot.bottom()))
        self._month_labels(painter)
        painter.end()
