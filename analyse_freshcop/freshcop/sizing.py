"""Dimensionnement dynamique et marges de puissance (§4.2.5 à §4.3.14).

Moteur de calcul de la puissance froid appelée heure par heure, puis lecture
des marges, saturations et sensibilités pour 2 / 2,5 / 3 MW.

Méthode (§4.2.5 et §4.3.14). La puissance est calculée sur une trajectoire
*contrôlée* par sous-groupe (zone × type de vitrage) : à chaque pas, on évalue
la température qu'atteindrait le sous-groupe à partir de son état contrôlé
courant ; si elle dépasse la consigne, on applique la puissance qui le ramène
à la consigne au pas suivant :

    Q_i(t) = max(0 ; [T_libre,i(t+1) - T_cible,i(t+1)]) · C_i / Δt
    C_i    = C_total · fraction_surface_i · fraction_vitrage_i

Le pic réactif est piloté par la transition de consigne des chambres à 20 h
(26 °C -> 24 °C), qui rend les chambres dimensionnantes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .calibration import ModeleRC
from .data import DonneesCalibration
from .simulation import consigne_zone


@dataclass
class ResultatPuissance:
    """Sortie du moteur de puissance pour un scénario et un mode donnés."""

    puissance: np.ndarray            # MW appelés heure par heure
    energie_MWh: float               # énergie froide sur la période
    pic_MW: float                    # pic non contraint
    heures_actives: int              # heures où Q > 0
    p95_actives: float               # P95 des heures actives
    energie_zone: dict               # MWh par zone
    energie_vitrage: dict            # MWh par type de vitrage


def puissance_froid(modele: ModeleRC, d: DonneesCalibration, delta_T: float,
                    capacite_surfacique: float = config.CAPACITE_SURFACIQUE_REF,
                    mode: str = "reactif",
                    seuil_actif_MW: float = 1e-6) -> ResultatPuissance:
    """Calcule la puissance froid appelée (pic non contraint, énergie, ...).

    Le calcul est dynamique : il ne suppose pas que tous les logements
    appellent leur puissance maximale en permanence ; il simule la dynamique
    horaire de la période observée translatée au climat considéré.
    """
    C_total = config.capacite_totale_MWh_par_K(capacite_surfacique)  # MWh/K
    Text = d.Text + delta_T
    n = len(d)
    Q = np.zeros(n)
    e_zone = {z.nom: 0.0 for z in config.ZONES}
    e_vitrage = {v.nom: 0.0 for v in config.VITRAGES}

    a, b, c = modele.a, modele.b, modele.c
    for zone in config.ZONES:
        cible = consigne_zone(zone, d.heure, mode)
        for vit in config.VITRAGES:
            Ci = C_total * zone.part_surface * vit.part_parc  # MWh/K
            Tc = d.Tint[0]  # état contrôlé initial
            for k in range(n - 1):
                # gain thermique horaire, amplifié/atténué selon le vitrage
                gain = vit.facteur * (a * (Text[k] - Tc) + b * d.Rad[k] + c)
                T_next = Tc + gain
                cible_next = cible[k + 1]
                if T_next > cible_next:
                    q = Ci * (T_next - cible_next) / config.PAS_HORAIRE_H  # MW
                    Q[k + 1] += q
                    e_zone[zone.nom] += q * config.PAS_HORAIRE_H
                    e_vitrage[vit.nom] += q * config.PAS_HORAIRE_H
                    Tc = cible_next  # ramené à la consigne
                else:
                    Tc = T_next

    actives = Q[Q > seuil_actif_MW]
    return ResultatPuissance(
        puissance=Q,
        energie_MWh=float(Q.sum() * config.PAS_HORAIRE_H),
        pic_MW=float(Q.max()),
        heures_actives=int(actives.size),
        p95_actives=float(np.percentile(actives, 95)) if actives.size else 0.0,
        energie_zone=e_zone,
        energie_vitrage=e_vitrage,
    )


# --------------------------------------------------------------------------
# §4.3.6 — Tableau de dimensionnement par scénario climatique
# --------------------------------------------------------------------------
def tableau_dimensionnement(modele: ModeleRC, d: DonneesCalibration,
                            capacite_surfacique: float = config.CAPACITE_SURFACIQUE_REF,
                            mode: str = "reactif") -> tuple[pd.DataFrame, dict]:
    """Pic non contraint, énergie, heures actives et P95 par scénario.

    Renvoie aussi le dictionnaire {scénario: ResultatPuissance} réutilisé par
    les tableaux de marges et de saturation.
    """
    lignes, resultats = [], {}
    for sc in config.SCENARIOS_CLIMAT:
        r = puissance_froid(modele, d, sc.delta_T, capacite_surfacique, mode)
        resultats[sc.nom] = r
        lignes.append({
            "Scénario": sc.nom,
            "Pic non contraint (MW)": r.pic_MW,
            "Énergie froide (MWh)": r.energie_MWh,
            "Heures actives": r.heures_actives,
            "P95 heures actives (MW)": r.p95_actives,
        })
    return pd.DataFrame(lignes).set_index("Scénario"), resultats


# --------------------------------------------------------------------------
# §4.3.7 / §4.4.1 — Marges de puissance 2 / 2,5 / 3 MW
# --------------------------------------------------------------------------
def tableau_marges(resultats: dict,
                   capacites=config.CAPACITES_INSTALLEES_MW) -> pd.DataFrame:
    """Marge = P_installée - pic non contraint, pour chaque scénario."""
    lignes = []
    for nom, r in resultats.items():
        ligne = {"Scénario": nom}
        for cap in capacites:
            ligne[f"Marge {cap:g} MW"] = cap - r.pic_MW
        lignes.append(ligne)
    return pd.DataFrame(lignes).set_index("Scénario")


# --------------------------------------------------------------------------
# §4.3.8 — Heures de saturation
# --------------------------------------------------------------------------
def tableau_saturation(resultats: dict,
                       capacites=config.CAPACITES_INSTALLEES_MW) -> pd.DataFrame:
    """Nombre d'heures où la puissance appelée dépasse la capacité installée."""
    lignes = []
    for nom, r in resultats.items():
        ligne = {"Scénario": nom}
        for cap in capacites:
            ligne[f"Saturation {cap:g} MW"] = int(np.sum(r.puissance > cap))
        lignes.append(ligne)
    return pd.DataFrame(lignes).set_index("Scénario")


# --------------------------------------------------------------------------
# §4.3.9 / §4.3.10 — Contribution des zones et du vitrage
# --------------------------------------------------------------------------
def contribution_zones(resultat: ResultatPuissance) -> pd.DataFrame:
    total = resultat.energie_MWh
    lignes = [{
        "Zone": z, "Énergie froide (MWh)": e,
        "Part du total": e / total if total else 0.0,
    } for z, e in resultat.energie_zone.items()]
    return pd.DataFrame(lignes).set_index("Zone")


def contribution_vitrage(resultat: ResultatPuissance) -> pd.DataFrame:
    total = resultat.energie_MWh
    parts = {v.nom: v.part_parc for v in config.VITRAGES}
    lignes = [{
        "Vitrage": v, "Hypothèse de parc": parts[v],
        "Énergie froide (MWh)": e,
        "Part du total": e / total if total else 0.0,
    } for v, e in resultat.energie_vitrage.items()]
    return pd.DataFrame(lignes).set_index("Vitrage")


# --------------------------------------------------------------------------
# §4.3.11 / §4.2.9 — Sensibilités de dimensionnement
# --------------------------------------------------------------------------
def sensibilite_dimensionnement(modele: ModeleRC, d: DonneesCalibration,
                                delta_T: float,
                                capacites=config.CAPACITES_SURFACIQUES_SENSIBILITE,
                                prudences=config.COEFFICIENTS_PRUDENCE) -> pd.DataFrame:
    """Pic et énergie 2050 selon capacité thermique et coefficient de prudence.

    Le coefficient de prudence majore le besoin pour couvrir l'hétérogénéité
    réelle des logements (étage, orientation, apports internes) (§4.3.11).
    """
    lignes = []
    for cap in capacites:
        base = puissance_froid(modele, d, delta_T, capacite_surfacique=cap)
        for k in prudences:
            lignes.append({
                "Capacité thermique (Wh/m².K)": cap,
                "Coefficient de prudence": k,
                "Pic (MW)": base.pic_MW * k,
                "Énergie (MWh)": base.energie_MWh * k,
            })
    return pd.DataFrame(lignes).set_index(
        ["Capacité thermique (Wh/m².K)", "Coefficient de prudence"])


def sensibilite_chambres(modele: ModeleRC, d: DonneesCalibration,
                         delta_T: float) -> pd.DataFrame:
    """Pic/énergie selon capacité thermique et pilotage des chambres (§4.2.9).

    « nuit seule » = pilotage réactif (24 °C de nuit) ;
    « 24h/24 »     = pilotage anticipatif (24 °C en continu).
    """
    lignes = []
    for cap in config.CAPACITES_SURFACIQUES_SENSIBILITE:
        for mode, lib in (("reactif", "nuit seule"), ("anticipatif", "24h/24")):
            r = puissance_froid(modele, d, delta_T, capacite_surfacique=cap, mode=mode)
            lignes.append({
                "Capacité thermique (Wh/m².K)": cap,
                "Chambres 24°C": lib,
                "Pic froid (MW)": r.pic_MW,
                "Énergie (MWh)": r.energie_MWh,
            })
    return pd.DataFrame(lignes).set_index(["Capacité thermique (Wh/m².K)", "Chambres 24°C"])


# --------------------------------------------------------------------------
# §4.3.4 / §4.3.12 — Effet du pilotage (réactif vs anticipatif)
# --------------------------------------------------------------------------
def comparaison_pilotage(modele: ModeleRC, d: DonneesCalibration,
                         delta_T: float) -> pd.DataFrame:
    """Pics et énergie comparés entre pilotage réactif et anticipatif."""
    lignes = []
    for mode, lib in (("reactif", "Pilotage réactif"),
                      ("anticipatif", "Pilotage anticipatif")):
        r = puissance_froid(modele, d, delta_T, mode=mode)
        lignes.append({
            "Mode": lib, "Pic (MW)": r.pic_MW, "Énergie (MWh)": r.energie_MWh,
        })
    return pd.DataFrame(lignes).set_index("Mode")


def courbe_duree_charge(modele: ModeleRC, d: DonneesCalibration,
                        delta_T: float, mode: str = "reactif") -> np.ndarray:
    """Courbe de durée de charge : puissances triées par ordre décroissant."""
    r = puissance_froid(modele, d, delta_T, mode=mode)
    return np.sort(r.puissance)[::-1]


# --------------------------------------------------------------------------
# §4.4 — Tableau de décision consolidé V3
# --------------------------------------------------------------------------
def tableau_decision(resultats: dict,
                     scenario_ref: str = config.SCENARIO_CENTRAL) -> pd.DataFrame:
    """Marge et saturation sur le pic de référence 2050, par capacité."""
    r = None
    for nom, res in resultats.items():
        if nom.startswith(scenario_ref):
            r = res
            break
    if r is None:
        raise KeyError(f"Scénario de référence introuvable : {scenario_ref}")
    lignes = []
    for cap in config.CAPACITES_INSTALLEES_MW:
        lignes.append({
            "Capacité": f"{cap:g} MW",
            "Marge sur pic (MW)": cap - r.pic_MW,
            "Heures de saturation": int(np.sum(r.puissance > cap)),
        })
    return pd.DataFrame(lignes).set_index("Capacité")
