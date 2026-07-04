"""Simulation dynamique sans rafraîchissement et projections (§4.2.1 à §4.2.4).

Reproduit :
    - §4.2.2  températures intérieures libres 2026 / 2050 / 2100 ;
    - §4.2.3  dépassement des cibles de confort par zone ;
    - §4.2.8  métrique V3 « nuits chaudes » (lecture par les occupants).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .calibration import ModeleRC, simuler_trajectoire
from .data import DonneesCalibration


# --------------------------------------------------------------------------
# §4.2.2 — Simulation libre sous scénario climatique
# --------------------------------------------------------------------------
def temperature_libre(modele: ModeleRC, d: DonneesCalibration,
                      delta_T: float) -> np.ndarray:
    """Température intérieure libre pour un delta climatique donné.

    Le rayonnement est conservé identique afin d'isoler l'effet de la hausse
    de température extérieure (§4.2.2).
    """
    return simuler_trajectoire(modele.a, modele.b, modele.c,
                               d.Text + delta_T, d.Rad, d.Tint[0])


def synthese_temperatures_libres(modele: ModeleRC, d: DonneesCalibration
                                 ) -> pd.DataFrame:
    """Tableau moyenne / max / P95 / heures > seuils pour chaque scénario."""
    lignes = []
    for sc in config.SCENARIOS_TEMPERATURE:
        T = temperature_libre(modele, d, sc.delta_T)
        lignes.append({
            "Scénario": sc.nom,
            "Moyenne °C": np.mean(T),
            "Maximum °C": np.max(T),
            "P95 °C": np.percentile(T, 95),
            "h >26°C": int(np.sum(T > 26)),
            "h >28°C": int(np.sum(T > 28)),
            "h >30°C": int(np.sum(T > 30)),
            "h >32°C": int(np.sum(T > 32)),
        })
    return pd.DataFrame(lignes).set_index("Scénario")


# --------------------------------------------------------------------------
# §4.2.3 — Cibles par zone et dépassements
# --------------------------------------------------------------------------
def consigne_zone(zone: config.Zone, heure: np.ndarray,
                  mode: str = "reactif") -> np.ndarray:
    """Série horaire de la consigne d'une zone.

    - mode 'reactif'    : consigne nocturne appliquée de 20 h à 8 h (§4.3.3) ;
    - mode 'anticipatif': consigne nocturne appliquée en continu (§4.3.3).
    """
    if mode == "anticipatif":
        return np.full(len(heure), zone.consigne_nuit)
    est_nuit = (heure >= config.NUIT_DEBUT_H) | (heure < config.NUIT_FIN_H)
    return np.where(est_nuit, zone.consigne_nuit, zone.consigne_jour)


def depassement_cibles(modele: ModeleRC, d: DonneesCalibration,
                       delta_T: float, mode: str = "reactif") -> pd.DataFrame:
    """Heures / degrés-heures / dépassement max par zone (température libre)."""
    T = temperature_libre(modele, d, delta_T)
    lignes = []
    for zone in config.ZONES:
        cible = consigne_zone(zone, d.heure, mode)
        ecart = np.maximum(T - cible, 0.0)
        lignes.append({
            "Zone": zone.nom,
            "Consigne": _lib_consigne(zone),
            "Heures de dépassement": int(np.sum(ecart > 0)),
            "Degrés-heures": float(np.sum(ecart) * config.PAS_HORAIRE_H),
            "Dépassement maximal °C": float(np.max(ecart)),
        })
    return pd.DataFrame(lignes).set_index("Zone")


def _lib_consigne(zone: config.Zone) -> str:
    if zone.consigne_jour == zone.consigne_nuit:
        return f"{zone.consigne_jour:.1f} °C"
    return f"{zone.consigne_nuit:.0f} °C nuit / {zone.consigne_jour:.0f} °C jour"


# --------------------------------------------------------------------------
# §4.2.8 — Métrique V3 : nuits chaudes
# --------------------------------------------------------------------------
@dataclass
class NuitsChaudes:
    h_sup: dict          # heures > seuil {26,28,30}
    jours_equiv_28: float
    nuits: dict          # nb de nuits chaudes par seuil {26,28,30}
    t_max_nuit: float


def nuits_chaudes(temperature: np.ndarray, heure: np.ndarray,
                  temps: pd.Series) -> NuitsChaudes:
    """Compte les nuits « chaudes » (§4.2.8).

    Une nuit s'analyse de 22 h à 7 h. Elle est classée chaude pour un seuil
    donné si la température le dépasse pendant au moins 6 heures.
    """
    est_nuit = (heure >= config.NUIT_ANALYSE_DEBUT_H) | (heure <= config.NUIT_ANALYSE_FIN_H)
    # identifiant de nuit : décaler de 8 h rattache le soir (22-23 h) et le
    # petit matin (0-7 h du lendemain) à une même date de nuit.
    ts = pd.to_datetime(temps).reset_index(drop=True)
    id_nuit = (ts - pd.Timedelta(hours=8)).dt.date.to_numpy()

    h_sup = {s: int(np.sum(temperature > s)) for s in config.SEUILS_NUITS_CHAUDES_C}
    nuits = {s: 0 for s in config.SEUILS_NUITS_CHAUDES_C}
    df = pd.DataFrame({"T": temperature, "nuit": est_nuit, "id": id_nuit})
    for _, g in df[df["nuit"]].groupby("id"):
        for s in config.SEUILS_NUITS_CHAUDES_C:
            if int(np.sum(g["T"].to_numpy() > s)) >= config.NUIT_DUREE_MIN_H:
                nuits[s] += 1
    # « jours équivalents > 28 °C » : degrés-heures>28 ramenés à des journées
    dh28 = float(np.sum(np.maximum(temperature - 28, 0.0)))
    jours_equiv = dh28 / 24.0
    t_max_nuit = float(np.max(temperature[est_nuit])) if est_nuit.any() else float("nan")
    return NuitsChaudes(h_sup=h_sup, jours_equiv_28=jours_equiv,
                        nuits=nuits, t_max_nuit=t_max_nuit)


def synthese_nuits_chaudes(modele: ModeleRC, d: DonneesCalibration) -> pd.DataFrame:
    """Tableau nuits chaudes pour 2026 / 2050 / 2100 sans rafraîchissement."""
    lignes = []
    for sc in config.SCENARIOS_TEMPERATURE:
        T = temperature_libre(modele, d, sc.delta_T)
        nc = nuits_chaudes(T, d.heure, d.temps)
        lignes.append({
            "Scénario": sc.nom,
            "h >26": nc.h_sup[26.0], "h >28": nc.h_sup[28.0], "h >30": nc.h_sup[30.0],
            "jours équiv. >28": round(nc.jours_equiv_28, 1),
            "nuits >26 ≥6h": nc.nuits[26.0],
            "nuits >28 ≥6h": nc.nuits[28.0],
            "nuits >30 ≥6h": nc.nuits[30.0],
            "T max nuit °C": round(nc.t_max_nuit, 1),
        })
    return pd.DataFrame(lignes).set_index("Scénario")
