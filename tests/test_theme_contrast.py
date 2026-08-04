"""Contrast guard for the colour tokens.

A palette can look right on the designer's monitor and still fail people with
low vision, so the pairs that actually occur in the UI are checked mechanically.
Targets follow WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text, control
borders and focus rings (1.4.3 / 1.4.11).

If a token changes and a pair drops below its target, this test names the pair.
"""

import pytest

from ui import theme

THEMES = [("light", theme.LIGHT), ("dark", theme.DARK)]

# (foreground, background, minimum ratio, what it is)
TEXT_PAIRS = [
    ("text", "bg", 4.5, "Fliesstext auf Seitenhintergrund"),
    ("text", "surface", 4.5, "Fliesstext auf Karte"),
    ("text", "surface_2", 4.5, "Fliesstext auf zweiter Flaeche"),
    ("text", "surface_3", 4.5, "Fliesstext auf dritter Flaeche"),
    ("text_muted", "surface", 4.5, "Sekundaertext auf Karte"),
    ("text_muted", "bg", 4.5, "Sekundaertext auf Seite"),
    ("text_faint", "surface", 4.5, "Hinweistext auf Karte"),
    ("text_faint", "bg", 4.5, "Hinweistext auf Seite"),
    ("primary", "surface", 4.5, "Akzent als Link/Tab-Text"),
    ("on_primary", "primary_btn", 4.5, "Beschriftung auf gefuelltem Knopf"),
    # Money colours must read both as a value on a card and as pill text.
    ("green", "surface", 4.5, "Plusbetrag auf Karte"),
    ("green", "green_soft", 4.5, "Plus-Plakette"),
    ("red", "surface", 4.5, "Minusbetrag auf Karte"),
    ("red", "red_soft", 4.5, "Minus-Plakette"),
    ("amber", "surface", 4.5, "Warnwert auf Karte"),
    ("amber", "amber_soft", 4.5, "Warn-Plakette"),
    ("blue", "surface", 4.5, "Infowert auf Karte"),
    ("blue", "blue_soft", 4.5, "Info-Plakette"),
    ("grey", "surface", 4.5, "Neutralwert auf Karte"),
    ("grey", "grey_soft", 4.5, "Neutral-Plakette"),
    # Sidebar is paper-toned now, so its text sits on the sidebar surface.
    ("sidebar_text", "sidebar", 4.5, "Navigationstext"),
    ("sidebar_text_active", "sidebar_active", 4.5, "aktiver Navigationstext"),
]

# Non-text contrast (WCAG 1.4.11): borders, focus rings, separators.
UI_PAIRS = [
    ("border_strong", "surface", 3.0, "Eingabefeld-Rand auf Karte"),
    ("border_strong", "bg", 3.0, "Steuerelement-Rand auf Seite"),
    ("border_strong", "surface_2", 3.0, "Rand auf zweiter Flaeche"),
    ("border_strong", "surface_3", 3.0, "Rand auf dritter Flaeche"),
    ("focus", "surface", 3.0, "Fokusring auf Karte"),
    ("focus", "bg", 3.0, "Fokusring auf Seite"),
]


@pytest.mark.parametrize("name,colors", THEMES)
@pytest.mark.parametrize("fg,bg,minimum,label", TEXT_PAIRS)
def test_text_contrast(name, colors, fg, bg, minimum, label):
    ratio = theme.contrast_ratio(colors[fg], colors[bg])
    assert ratio >= minimum, (
        f"{name}: {label} ({fg} auf {bg}) nur {ratio:.2f}:1, "
        f"gefordert {minimum}:1")


@pytest.mark.parametrize("name,colors", THEMES)
@pytest.mark.parametrize("fg,bg,minimum,label", UI_PAIRS)
def test_ui_contrast(name, colors, fg, bg, minimum, label):
    ratio = theme.contrast_ratio(colors[fg], colors[bg])
    assert ratio >= minimum, (
        f"{name}: {label} ({fg} auf {bg}) nur {ratio:.2f}:1, "
        f"gefordert {minimum}:1")


@pytest.mark.parametrize("name,colors", THEMES)
def test_chart_series_are_distinguishable_from_the_surface(name, colors):
    """Every categorical colour must be visible as a filled shape (>=3:1)."""
    for i, hex_color in enumerate(colors["chart"]):
        ratio = theme.contrast_ratio(hex_color, colors["surface"])
        assert ratio >= 3.0, (
            f"{name}: Diagrammfarbe {i} ({hex_color}) nur {ratio:.2f}:1 "
            f"gegen die Kartenflaeche")


@pytest.mark.parametrize("name,colors", THEMES)
def test_both_themes_define_the_same_tokens(name, colors):
    """A key missing in one theme is a KeyError at runtime, in that theme only."""
    other = theme.DARK if name == "light" else theme.LIGHT
    assert set(colors) == set(other)


def test_sidebar_is_not_a_dark_slab_in_the_light_theme():
    """The near-black sidebar next to white content was the strongest ageing
    signal of the old design. It must stay part of the page."""
    ratio = theme.contrast_ratio(theme.LIGHT["sidebar"], theme.LIGHT["bg"])
    assert ratio < 1.5, "Seitenleiste hebt sich zu stark von der Seite ab"
    assert theme.contrast_ratio(theme.LIGHT["sidebar"], "#ffffff") < 2.0


def test_money_colours_are_not_the_brand_colour():
    """Green/red carry the direction of an amount; the accent carries the brand.
    If they collide, a positive amount starts reading as 'branded'."""
    for colors in (theme.LIGHT, theme.DARK):
        assert colors["green"] != colors["primary"]
        assert colors["red"] != colors["primary"]
        assert colors["primary"] not in (colors["green"], colors["red"])
