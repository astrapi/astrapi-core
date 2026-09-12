# core/ui/color_palette.py
"""Feste Farbpalette fuer das 'color_palette'-Formularfeld
(field_renderer.html) -- ersetzt den nativen `<input type="color">`-
Farbwaehler dort, wo eine begrenzte, optisch unterscheidbare Auswahl
gewuenscht ist (z.B. Ordner-Kategorien) statt beliebiger Hex-Werte.

32 Farben, erzeugt aus 16 gleichmaessig verteilten Farbtoenen (Hue) mit
zwei abwechselnden Helligkeiten (L=0.55/0.62, S=0.62) -- Nachbartoene
bleiben dadurch auf einen Blick unterscheidbar statt in einem reinen
Regenbogen zu verschwimmen."""

DEFAULT_COLOR_PALETTE = [
    "#d34545", "#da7962", "#d37a45", "#daa662", "#d3b045", "#dad362", "#c2d345", "#b5da62",
    "#8cd345", "#88da62", "#57d345", "#62da6a", "#45d369", "#62da97", "#45d39e", "#62dac4",
    "#45d3d3", "#62c4da", "#459ed3", "#6297da", "#4569d3", "#626ada", "#5745d3", "#8862da",
    "#8c45d3", "#b562da", "#c245d3", "#da62d3", "#d345b0", "#da62a6", "#d3457a", "#da6279",
]


def color_palette() -> list[str]:
    return DEFAULT_COLOR_PALETTE
