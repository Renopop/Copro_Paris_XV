"""Cœur du module interactif : hypothèses modifiables + calcul complet.

Ce module sépare la LOGIQUE (testable, sans dépendance à l'UI) de l'interface
Streamlit (``app_interactif.py``). Toutes les hypothèses du Chapitre 4 sont
regroupées dans :class:`Hypotheses` ; :func:`calculer_tout` les applique et
renvoie l'ensemble des résultats prêts à afficher.

Principe d'application : le moteur (`simulation`, `sizing`) lit les constantes
``config.*`` au moment de l'appel. :func:`appliquer` réinjecte donc les
hypothèses dans le module ``config`` avant chaque calcul — sans modifier le
moteur validé par les tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import config, calibration, simulation, sizing
from .data import DonneesCalibration


# --------------------------------------------------------------------------
# Jeu d'hypothèses modifiable
# --------------------------------------------------------------------------
@dataclass
class ZoneH:
    nom: str
    part_surface: float
    consigne_jour: float
    consigne_nuit: float


@dataclass
class Hypotheses:
    """Toutes les hypothèses du modèle, valeurs par défaut = document V3."""

    # Résidence (§4.4)
    nb_logements: int = 440
    surface_moy_logement: float = 80.0

    # Calibration / conversion (§4.7, §4.9)
    coeffs: str = "one_step"                 # "one_step" (P2/3) ou "free_run" (P1)
    capacite_surfacique: float = 120.0       # Wh/m².K

    # Climat (§4.3.6) — nom stable, delta ajustable
    scenarios: list = field(default_factory=lambda: [
        ["2026 mesuré", 0.0], ["2035 +1,0 °C", 1.0], ["2050 +2,2 °C", 2.2],
        ["2100 +3,2 °C", 3.2], ["Stress +4,0 °C", 4.0]])
    delta_focus: float = 2.2                 # scénario mis en avant (2050)

    # Zones de confort (§4.2.3)
    zones: list = field(default_factory=lambda: [
        ZoneH("Séjour", 0.33, 26.0, 26.0),
        ZoneH("Chambres", 0.33, 26.0, 24.0),
        ZoneH("Pièces secondaires", 0.34, 26.5, 26.5)])

    # Vitrage (§4.2.4)
    part_simple: float = 0.60
    facteur_simple: float = 1.15
    facteur_double: float = 0.775

    # Pilotage (§4.3.3)
    mode: str = "reactif"                     # "reactif" ou "anticipatif"
    nuit_debut_h: int = 20
    nuit_fin_h: int = 8

    # Capacités et robustesse (§4.3.7, §4.3.11)
    capacites_installees: tuple = (2.0, 2.5, 3.0)
    prudences: tuple = (1.0, 1.5, 2.0)

    # Nuits chaudes (§4.2.8)
    seuils_nuits: tuple = (26.0, 28.0, 30.0)

    # -- Contrôles de cohérence -------------------------------------------
    @property
    def surface_totale(self) -> float:
        return self.nb_logements * self.surface_moy_logement

    @property
    def part_double(self) -> float:
        return 1.0 - self.part_simple

    @property
    def somme_parts_zones(self) -> float:
        return sum(z.part_surface for z in self.zones)

    @property
    def facteur_vitrage_moyen(self) -> float:
        return self.part_simple * self.facteur_simple + self.part_double * self.facteur_double


def defaut() -> Hypotheses:
    """Hypothèses de référence du document (pour le bouton « réinitialiser »)."""
    return Hypotheses()


# --------------------------------------------------------------------------
# Application des hypothèses sur le module config
# --------------------------------------------------------------------------
def appliquer(h: Hypotheses) -> None:
    """Réinjecte les hypothèses dans ``config`` avant appel du moteur."""
    config.NB_LOGEMENTS = h.nb_logements
    config.SURFACE_MOY_LOGEMENT_M2 = h.surface_moy_logement
    config.SURFACE_TOTALE_M2 = h.surface_totale
    config.CAPACITE_SURFACIQUE_REF = h.capacite_surfacique
    config.ZONES = tuple(
        config.Zone(z.nom, z.part_surface, z.consigne_jour, z.consigne_nuit)
        for z in h.zones)
    config.VITRAGES = (
        config.Vitrage("Simple vitrage", h.part_simple, h.facteur_simple),
        config.Vitrage("Double vitrage", h.part_double, h.facteur_double))
    config.NUIT_DEBUT_H = h.nuit_debut_h
    config.NUIT_FIN_H = h.nuit_fin_h
    config.CAPACITES_INSTALLEES_MW = tuple(h.capacites_installees)
    config.COEFFICIENTS_PRUDENCE = tuple(h.prudences)
    config.SEUILS_NUITS_CHAUDES_C = tuple(h.seuils_nuits)
    config.CAPACITES_SURFACIQUES_SENSIBILITE = tuple(sorted({
        80.0, h.capacite_surfacique, 165.0}))
    config.SCENARIOS_CLIMAT = tuple(
        config.ScenarioClimatique(nom, dt) for nom, dt in h.scenarios)


# --------------------------------------------------------------------------
# Calcul complet
# --------------------------------------------------------------------------
def calculer_tout(h: Hypotheses, d: DonneesCalibration,
                  modele_p1: calibration.ModeleRC,
                  modele_os: calibration.ModeleRC) -> dict:
    """Applique les hypothèses et renvoie tous les résultats à afficher.

    ``modele_p1`` / ``modele_os`` sont fournis (mis en cache) car la
    calibration ne dépend que du CSV et de la méthode, pas des autres
    hypothèses.
    """
    appliquer(h)
    modele = modele_os if h.coeffs == "one_step" else modele_p1

    # --- Focus (scénario mis en avant) ---
    focus = sizing.puissance_froid(modele, d, h.delta_focus, h.capacite_surfacique,
                                   mode=h.mode)

    # --- Partie 3 : dimensionnement par scénario ---
    dim, resultats = sizing.tableau_dimensionnement(
        modele, d, h.capacite_surfacique, mode=h.mode)
    marges = sizing.tableau_marges(resultats)
    saturation = sizing.tableau_saturation(resultats)

    # --- Décision (sur le scénario focus, robuste au renommage) ---
    decision = pd.DataFrame([{
        "Capacité": f"{cap:g} MW",
        "Marge sur pic (MW)": cap - focus.pic_MW,
        "Heures de saturation": int(np.sum(focus.puissance > cap)),
    } for cap in h.capacites_installees]).set_index("Capacité")
    capacite_reco = _capacite_recommandee(focus, h.capacites_installees)

    # --- Courbes ---
    Q_focus = focus.puissance
    cdc_reac = sizing.courbe_duree_charge(modele, d, h.delta_focus, "reactif")
    cdc_anti = sizing.courbe_duree_charge(modele, d, h.delta_focus, "anticipatif")

    return {
        "modele": modele,
        # Partie 1
        "conversion": calibration.conversion_grandeurs_physiques(
            modele, surface_m2=h.surface_totale),
        # Partie 2
        "temperatures_libres": simulation.synthese_temperatures_libres(modele, d),
        "depassement": simulation.depassement_cibles(modele, d, h.delta_focus, h.mode),
        "nuits_chaudes": simulation.synthese_nuits_chaudes(modele, d),
        "sensibilite_chambres": sizing.sensibilite_chambres(modele, d, h.delta_focus),
        # Partie 3
        "dimensionnement": dim,
        "marges": marges,
        "saturation": saturation,
        "contribution_zones": sizing.contribution_zones(focus),
        "contribution_vitrage": sizing.contribution_vitrage(focus),
        "sensibilite_dimensionnement": sizing.sensibilite_dimensionnement(
            modele, d, h.delta_focus),
        "comparaison_pilotage": sizing.comparaison_pilotage(modele, d, h.delta_focus),
        # Partie 4
        "decision": decision,
        "capacite_recommandee": capacite_reco,
        # Focus + courbes
        "focus": focus,
        "temps": d.temps,
        "Q_focus": Q_focus,
        "courbe_duree_reactif": cdc_reac,
        "courbe_duree_anticipatif": cdc_anti,
    }


def _capacite_recommandee(focus: sizing.ResultatPuissance,
                          capacites) -> float | None:
    """Plus petite capacité éliminant la saturation sur le scénario focus."""
    for cap in sorted(capacites):
        if np.sum(focus.puissance > cap) == 0:
            return cap
    return None
