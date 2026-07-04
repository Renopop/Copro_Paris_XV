"""Modèle thermique dynamique FRESHCOP — Chapitre 4 consolidé (V3).

Package reproduisant l'ensemble des analyses et calculs du document
``FRESHCOP_Chapitre4_Consolide_Corrections_V3_Recentrage_1_2_3.docx``,
calibrés sur le fichier ``T appart mai - jin 26.csv``.

Modules
-------
config      : hypothèses et constantes (mesuré / identifié / supposé).
data        : lecture CSV, cadrage période, moyenne AB/CD (§4.2).
stats       : statistiques, degrés-heures, déphasage, nuit (§4.3, §4.8).
calibration : identification du modèle RC (§4.5-4.9).
simulation  : températures libres, zones, nuits chaudes (§4.2.x).
sizing      : puissance froid, marges, saturation, sensibilités (§4.3.x).
figures     : figures matplotlib.
"""

from . import config, data, stats, calibration, simulation, sizing  # noqa: F401

__all__ = ["config", "data", "stats", "calibration", "simulation", "sizing"]
__version__ = "3.0"
