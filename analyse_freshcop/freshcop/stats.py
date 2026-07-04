"""Statistiques descriptives et analyses dynamiques (§4.3 et §4.8).

Reproduit :
    - §4.3  statistiques descriptives (moyenne, médiane, min, max, P95) ;
    - §4.3  heures de dépassement et degrés-heures par seuil ;
    - §4.8  déphasage par corrélation croisée (brute et détendancée) ;
    - §4.8  refroidissement nocturne extérieur disponible vs. baisse intérieure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .data import DonneesCalibration


# --------------------------------------------------------------------------
# §4.3 — Statistiques descriptives
# --------------------------------------------------------------------------
def statistiques_descriptives(d: DonneesCalibration) -> pd.DataFrame:
    """Tableau moyenne / médiane / min / max / P95 des grandeurs mesurées."""
    series = {
        "Température extérieure": d.Text,
        "Circuit AB": d.Tint_AB,
        "Circuit CD": d.Tint_CD,
        "Moyenne AB/CD": d.Tint,
        "Rayonnement direct": d.Rad,
        "Précipitations": d.Pluie,
    }
    lignes = []
    for nom, x in series.items():
        lignes.append({
            "Grandeur": nom,
            "Moyenne": np.mean(x),
            "Médiane": np.median(x),
            "Minimum": np.min(x),
            "Maximum": np.max(x),
            "P95": np.percentile(x, 95),
        })
    return pd.DataFrame(lignes).set_index("Grandeur")


def degres_heures(temperature: np.ndarray,
                  seuils=config.SEUILS_DEPASSEMENT_C,
                  pas_h: float = config.PAS_HORAIRE_H) -> pd.DataFrame:
    """Heures de dépassement, part de la période et degrés-heures cumulés.

    Degrés-heures au-dessus d'un seuil S = Somme max(Tint - S, 0) (Annexe A).
    """
    n = len(temperature)
    lignes = []
    for s in seuils:
        depasse = temperature > s
        dh = np.sum(np.maximum(temperature - s, 0.0)) * pas_h
        lignes.append({
            "Seuil": f">{s:.0f} °C",
            "Heures": int(depasse.sum()),
            "Part de la période": depasse.mean(),
            "Degrés-heures": dh,
        })
    return pd.DataFrame(lignes).set_index("Seuil")


# --------------------------------------------------------------------------
# §4.8 — Déphasage / inertie par corrélation croisée
# --------------------------------------------------------------------------
@dataclass
class ResultatDephasage:
    lag_brut_h: int
    r_brut: float
    lag_detendance_h: int
    r_detendance: float
    correlation_brute: np.ndarray       # r en fonction du décalage (0..lag_max)
    correlation_detendance: np.ndarray


def _correlation_decalee(x: np.ndarray, y: np.ndarray, lag_max: int) -> np.ndarray:
    """Corrélation de Pearson entre x(t-lag) et y(t) pour lag = 0..lag_max.

    Le décalage positif signifie que l'extérieur *précède* l'intérieur.
    """
    r = np.empty(lag_max + 1)
    for lag in range(lag_max + 1):
        if lag == 0:
            xa, ya = x, y
        else:
            xa, ya = x[:-lag], y[lag:]
        r[lag] = np.corrcoef(xa, ya)[0, 1]
    return r


def dephasage(d: DonneesCalibration, lag_max: int = 72) -> ResultatDephasage:
    """Corrélation brute (mémoire lente) et détendancée (réponse journalière).

    - Brute : maximum vers ~51 h -> effet mémoire/canicule sur plusieurs jours.
    - Détendancée (retrait de la moyenne glissante 24 h) : maximum vers ~3 h,
      déphasage du cycle jour/nuit.
    """
    ext, intr = d.Text, d.Tint
    corr_brute = _correlation_decalee(ext, intr, lag_max)
    lag_brut = int(np.argmax(corr_brute))

    # Détendançage : retrait de la composante moyenne 24 h
    ext_d = ext - pd.Series(ext).rolling(24, center=True, min_periods=1).mean().to_numpy()
    intr_d = intr - pd.Series(intr).rolling(24, center=True, min_periods=1).mean().to_numpy()
    corr_det = _correlation_decalee(ext_d, intr_d, lag_max)
    lag_det = int(np.argmax(corr_det))

    return ResultatDephasage(
        lag_brut_h=lag_brut, r_brut=float(corr_brute[lag_brut]),
        lag_detendance_h=lag_det, r_detendance=float(corr_det[lag_det]),
        correlation_brute=corr_brute, correlation_detendance=corr_det,
    )


# --------------------------------------------------------------------------
# §4.8 — Refroidissement nocturne
# --------------------------------------------------------------------------
@dataclass
class RefroidissementNocturne:
    baisse_ext_moy: float   # °C de baisse extérieure moyenne 20 h -> 6 h
    baisse_int_moy: float   # °C de baisse intérieure moyenne sur la même plage
    taux_recuperation: float  # part de la fraîcheur extérieure récupérée


def refroidissement_nocturne(d: DonneesCalibration,
                             h_debut: int = 20, h_fin: int = 6) -> RefroidissementNocturne:
    """Baisse extérieure disponible vs. baisse intérieure réellement observée.

    Pour chaque nuit, on compare la température à ``h_debut`` (20 h) à celle
    de ``h_fin`` (6 h le lendemain matin).
    """
    df = pd.DataFrame({
        "t": d.temps.to_numpy(),
        "Text": d.Text, "Tint": d.Tint,
        "h": d.heure,
    })
    baisses_ext, baisses_int = [], []
    n = len(df)
    idx_debut = np.where(df["h"].to_numpy() == h_debut)[0]
    for i in idx_debut:
        # cherche la première occurrence de h_fin après i (<= 14 h plus tard)
        for j in range(i + 1, min(i + 15, n)):
            if df["h"].iloc[j] == h_fin:
                baisses_ext.append(df["Text"].iloc[i] - df["Text"].iloc[j])
                baisses_int.append(df["Tint"].iloc[i] - df["Tint"].iloc[j])
                break
    baisse_ext = float(np.mean(baisses_ext)) if baisses_ext else float("nan")
    baisse_int = float(np.mean(baisses_int)) if baisses_int else float("nan")
    taux = baisse_int / baisse_ext if baisse_ext else float("nan")
    return RefroidissementNocturne(baisse_ext, baisse_int, taux)
