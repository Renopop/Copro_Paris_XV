"""Lecture, nettoyage et cadrage temporel du CSV (§4.2, Annexe A étapes 1-3).

Étapes reproduites :
    1. Lecture du CSV et conversion des colonnes numériques.
    2. Exclusion des lignes antérieures au 22 mai 2026 (chauffage collectif).
    3. Construction de la température intérieure moyenne AB/CD.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


@dataclass
class DonneesCalibration:
    """Série horaire retenue pour la calibration (960 heures)."""

    temps: pd.Series      # horodatage
    Text: np.ndarray      # température extérieure (°C)
    Tint_AB: np.ndarray   # circuit AB (°C)
    Tint_CD: np.ndarray   # circuit CD (°C)
    Tint: np.ndarray      # moyenne AB/CD (°C)
    Rad: np.ndarray       # rayonnement direct normal (W/m²)
    Pluie: np.ndarray     # précipitations (mm/h)
    heure: np.ndarray     # heure de la journée (0-23), entier

    def __len__(self) -> int:
        return len(self.Tint)


def charger_csv(chemin_csv: str) -> pd.DataFrame:
    """Étape 1 — lecture brute et normalisation des colonnes.

    Le CSV utilise le séparateur ';', le point décimal, et comporte des
    colonnes vides en fin de ligne (ignorées).
    """
    df = pd.read_csv(chemin_csv, sep=";", decimal=".")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=config.COLONNES_CSV)
    # Conversion numérique robuste
    for col in ("Text", "Tint_AB", "Tint_CD", "Rad", "Pluie"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["temps"] = pd.to_datetime(df["Date_Heure"], format="%d/%m/%Y %H:%M")
    return df


def cadrer_periode(df: pd.DataFrame) -> pd.DataFrame:
    """Étape 2 — ne conserve que la période postérieure à l'arrêt chauffage."""
    debut = pd.Timestamp(config.DEBUT_CALIBRATION)
    fin = pd.Timestamp(config.FIN_CALIBRATION)
    masque = (df["temps"] >= debut) & (df["temps"] <= fin)
    return df.loc[masque].reset_index(drop=True)


def preparer(chemin_csv: str) -> DonneesCalibration:
    """Chaîne complète 1->3 : renvoie les tableaux prêts pour la calibration."""
    df = cadrer_periode(charger_csv(chemin_csv))
    if len(df) == 0:
        raise ValueError("Aucune ligne sur la période de calibration — "
                         "vérifier le chemin ou le format du CSV.")
    # Étape 3 — moyenne AB/CD (Tint = (Tint_AB + Tint_CD) / 2)
    tint = (df["Tint_AB"].to_numpy() + df["Tint_CD"].to_numpy()) / 2.0
    return DonneesCalibration(
        temps=df["temps"],
        Text=df["Text"].to_numpy(dtype=float),
        Tint_AB=df["Tint_AB"].to_numpy(dtype=float),
        Tint_CD=df["Tint_CD"].to_numpy(dtype=float),
        Tint=tint,
        Rad=df["Rad"].to_numpy(dtype=float),
        Pluie=df["Pluie"].to_numpy(dtype=float),
        heure=df["temps"].dt.hour.to_numpy(dtype=int),
    )
