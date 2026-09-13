# core/ui/color_palette.py
"""Feste Farbpalette fuer das 'color_palette'-Formularfeld
(field_renderer.html) -- ersetzt den nativen `<input type="color">`-
Farbwaehler dort, wo eine begrenzte, optisch unterscheidbare Auswahl
gewuenscht ist (z.B. Ordner-/Item-Kategorien) statt beliebiger Hex-Werte.

12 Farben, von Hand gewaehlt statt gleichmaessig um den Farbkreis rotiert
-- eine rein formelhafte Hue-Rotation (frueher: 32, dann 16 Toene bei
gleicher Saettigung/Helligkeit) haeufte mehrere kaum unterscheidbare
Gruen-/Blautoene nebeneinander an, weil das menschliche Auge Farbtoene
dort schlechter unterscheidet als bei Rot/Orange/Violett (auf
Nutzerfeedback am echten Bildschirm reduziert). Braun/Grau ergaenzen die
reinen Spektralfarben, weil sie kategorial anders wahrgenommen werden
als jede Hue-Rotation -- zusaetzlicher Kontrast ohne weitere,
schwer unterscheidbare Zwischentoene."""

DEFAULT_COLOR_PALETTE = [
    "#e53e3e",  # Rot
    "#ed8936",  # Orange
    "#d69e2e",  # Gold/Amber
    "#38a169",  # Grün
    "#319795",  # Türkis
    "#00b5d8",  # Cyan
    "#3182ce",  # Blau
    "#5a67d8",  # Indigo
    "#805ad5",  # Violett
    "#d53f8c",  # Magenta/Pink
    "#975a16",  # Braun
    "#718096",  # Grau
]


def color_palette() -> list[str]:
    return DEFAULT_COLOR_PALETTE
