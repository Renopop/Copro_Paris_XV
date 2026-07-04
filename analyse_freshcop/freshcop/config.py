"""Constantes et hypothèses du Chapitre 4 consolidé FRESHCOP (V3).

Toutes les valeurs proviennent du document
``FRESHCOP_Chapitre4_Consolide_Corrections_V3_Recentrage_1_2_3.docx``.
Chaque constante est annotée avec la section source, et son statut :
    - mesuré   : lu directement dans le CSV / donnée résidence
    - identifié : issu d'une régression sur les mesures
    - supposé  : hypothèse de scénario / de conversion

Le principe de séparation « mesuré / identifié / supposé » est celui du §4.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Période de calibration (§4.2) — mesuré
# --------------------------------------------------------------------------
# Le chauffage collectif est arrêté le 22/05/2026 : la calibration ne retient
# que les 960 heures postérieures, sans influence résiduelle du chauffage.
DEBUT_CALIBRATION = "2026-05-22 00:00"
FIN_CALIBRATION = "2026-06-30 23:00"
PAS_HORAIRE_H = 1.0  # pas de temps du modèle (heure)

# Correspondance colonnes CSV -> noms internes (§4.2)
COLONNES_CSV = {
    "weather_air_temperature": "Text",
    "REFERENCE EFFICAP - Circuit AB": "Tint_AB",
    "REFERENCE EFFICAP - Circuit CD": "Tint_CD",
    "weather_direct_normal_radiation": "Rad",
    "weather_precipitation": "Pluie",
}

# --------------------------------------------------------------------------
# Données résidence (§4.4) — mesuré / donnée résidence
# --------------------------------------------------------------------------
NB_LOGEMENTS = 440             # donnée résidence
SURFACE_MOY_LOGEMENT_M2 = 80.0  # donnée résidence (à confirmer par plans)
SURFACE_TOTALE_M2 = NB_LOGEMENTS * SURFACE_MOY_LOGEMENT_M2  # 35 200 m²

# --------------------------------------------------------------------------
# Conversion coefficients apparents -> grandeurs physiques (§4.9) — supposé
# --------------------------------------------------------------------------
# Capacité thermique surfacique effective (Wh/m².K).
CAPACITE_SURFACIQUE_REF = 120.0        # valeur de référence retenue
CAPACITE_SURFACIQUE_PLAGE = (80.0, 165.0)  # plage de sensibilité
CAPACITES_SURFACIQUES_SENSIBILITE = (80.0, 120.0, 165.0)


def capacite_totale_MWh_par_K(capacite_surfacique_Wh_m2K: float,
                              surface_m2: float | None = None) -> float:
    """C = Surface × capacité surfacique (§4.9, Annexe A).

    Wh/m².K × m² = Wh/K ; conversion en MWh/K (÷ 1e6).

    ``surface_m2=None`` lit la surface courante du module (permet au module
    interactif de modifier la surface à la volée sans refactorer le moteur).
    """
    if surface_m2 is None:
        surface_m2 = SURFACE_TOTALE_M2
    return capacite_surfacique_Wh_m2K * surface_m2 / 1.0e6


# --------------------------------------------------------------------------
# Coefficients du modèle RC (§4.6 / §4.7 et §4.2.1) — identifié
# --------------------------------------------------------------------------
# Le document présente DEUX jeux de coefficients, tous deux reproductibles
# à partir du CSV (cf. freshcop.calibration) :
#
#   - Partie 1 (référence de calibration V3) : ajustement sur la TRAJECTOIRE
#     libre (free-run). tau = 330 h, RMSE 1.32 °C, R² 0.81.
#   - Parties 2 & 3 (simulations/dimensionnement) : moindres carrés à un pas
#     (one-step). tau = 275 h, RMSE 1.73 °C, R² 0.67.
#
# Les simulations de puissance (parties 2/3) utilisent le jeu one-step, seul
# jeu qui reproduit exactement les pics documentés (2.65 MW en 2050).

COEFF_PARTIE1 = {"a": 0.003035, "b": 0.00012597, "c": -0.01829}   # free-run
COEFF_PARTIE23 = {"a": 0.00363, "b": 0.0001462, "c": -0.0270}      # one-step

# Valeurs de validation documentées (pour comparer aux calculs)
VALIDATION_PARTIE1 = {"tau_h": 330.0, "rmse": 1.32, "mae": 1.07,
                      "biais": -0.08, "r2": 0.81}
VALIDATION_PARTIE23 = {"tau_h": 275.0, "rmse": 1.73, "mae": 1.49, "r2": 0.67}

# --------------------------------------------------------------------------
# Seuils d'analyse thermique (§4.3) — supposé (seuils de confort)
# --------------------------------------------------------------------------
SEUILS_DEPASSEMENT_C = (24.0, 26.0, 28.0, 30.0, 32.0)

# --------------------------------------------------------------------------
# Scénarios climatiques (§4.2.2 et §4.3.6) — supposé
# --------------------------------------------------------------------------
# Delta appliqué à la température extérieure ; le rayonnement est conservé
# afin d'isoler l'effet de la hausse de température.
@dataclass(frozen=True)
class ScenarioClimatique:
    nom: str
    delta_T: float  # °C ajoutés à la température extérieure


SCENARIOS_CLIMAT = (
    ScenarioClimatique("2026 mesuré", 0.0),
    ScenarioClimatique("2035 +1,0 °C", 1.0),
    ScenarioClimatique("2050 +2,2 °C", 2.2),
    ScenarioClimatique("2100 +3,2 °C", 3.2),
    ScenarioClimatique("Stress +4,0 °C", 4.0),
)
# Scénarios utilisés pour les températures libres de la partie 2
SCENARIOS_TEMPERATURE = (
    ScenarioClimatique("2026 sans froid", 0.0),
    ScenarioClimatique("2050 +2,2 °C sans froid", 2.2),
    ScenarioClimatique("2100 +3,2 °C sans froid", 3.2),
)
SCENARIO_CENTRAL = "2050 +2,2 °C"  # scénario de dimensionnement de référence

# --------------------------------------------------------------------------
# Zones de confort et consignes (§4.2.3 / §4.3.3) — supposé
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Zone:
    nom: str
    part_surface: float      # fraction de la surface totale
    consigne_jour: float     # °C consigne diurne
    consigne_nuit: float     # °C consigne nocturne


ZONES = (
    Zone("Séjour", 0.33, 26.0, 26.0),
    Zone("Chambres", 0.33, 26.0, 24.0),      # 24 °C la nuit = hypothèse dimensionnante
    Zone("Pièces secondaires", 0.34, 26.5, 26.5),
)

# Fenêtre nocturne pour le pilotage réactif des chambres (§4.3.3 : 20 h -> 8 h)
NUIT_DEBUT_H = 20   # inclus
NUIT_FIN_H = 8      # exclu (heures < 8)

# --------------------------------------------------------------------------
# Répartition et pondération du vitrage (§4.2.4 / §4.3.10) — supposé
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Vitrage:
    nom: str
    part_parc: float   # fraction du parc de logements
    facteur: float     # facteur de gain apparent (amplifie le gain horaire)


VITRAGES = (
    Vitrage("Simple vitrage", 0.60, 1.15),   # plus sensible aux apports
    Vitrage("Double vitrage", 0.40, 0.775),  # choisi pour conserver la moyenne
)
# Contrôle : 0,60×1,15 + 0,40×0,775 = 1,00 (moyenne pondérée cohérente CSV)

# --------------------------------------------------------------------------
# Capacités de production froid étudiées (§4.2.6 / §4.3.7) — supposé
# --------------------------------------------------------------------------
CAPACITES_INSTALLEES_MW = (2.0, 2.5, 3.0)

# Coefficients de prudence testés en sensibilité de dimensionnement (§4.3.11)
COEFFICIENTS_PRUDENCE = (1.0, 1.5, 2.0)

# --------------------------------------------------------------------------
# Métrique « nuits chaudes » V3 (§4.2.8) — supposé (critère de décision)
# --------------------------------------------------------------------------
NUIT_ANALYSE_DEBUT_H = 22   # une nuit est analysée de 22 h à 7 h
NUIT_ANALYSE_FIN_H = 7
NUIT_DUREE_MIN_H = 6        # nuit « chaude » si dépassement >= 6 heures
SEUILS_NUITS_CHAUDES_C = (26.0, 28.0, 30.0)


@dataclass
class ConfigModele:
    """Regroupe les paramètres pilotables d'une exécution complète."""

    chemin_csv: str = "T appart mai - jin 26.csv"
    dossier_sorties: str = "sorties"
    # jeu de coefficients pour les simulations de puissance :
    #   "one_step" (parties 2/3, défaut) ou "free_run" (partie 1)
    coeffs_simulation: str = "one_step"
    capacite_surfacique: float = CAPACITE_SURFACIQUE_REF
    generer_figures: bool = True
