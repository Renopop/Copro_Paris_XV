"""Construction et calibration du modèle RC dynamique (§4.5 à §4.9).

Modèle conceptuel 2R2C (§4.6) :
    C_m · dT_m/dt = (T_ext - T_m)/R1 - (T_m - T_air)/R2 + Q_solaire
    C_air · dT_air/dt = (T_m - T_air)/R2 + Q_internes - Q_froid

Forme discrète identifiable, à pas horaire (§4.6) :
    T_int(t+1) = T_int(t) + a·[T_ext(t) - T_int(t)] + b·Rad(t) + c

Deux méthodes d'identification, toutes deux reproductibles sur le CSV :
    - one_step : moindres carrés à un pas sur l'incrément ΔT_int
                 -> coefficients des parties 2 & 3 (tau ≈ 275 h, R² ≈ 0.67).
    - free_run : minimisation de l'erreur sur la trajectoire libre simulée
                 -> coefficients de la partie 1 (tau ≈ 330 h, R² ≈ 0.81).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import config
from .data import DonneesCalibration


@dataclass
class ModeleRC:
    """Modèle RC équivalent identifié + indicateurs de validation."""

    a: float   # couplage thermique apparent intérieur/extérieur (h⁻¹)
    b: float   # sensibilité apparente au rayonnement (K par W/m².h)
    c: float   # terme résiduel : ventilation, apports internes, biais (K/h)
    methode: str
    rmse: float
    mae: float
    biais: float
    r2: float
    tau_h: float          # constante de temps équivalente = 1/a
    simulation: np.ndarray  # trajectoire libre simulée (pour les figures)

    @property
    def tau_jours(self) -> float:
        return self.tau_h / 24.0

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "c": self.c}


def simuler_trajectoire(a: float, b: float, c: float,
                        Text: np.ndarray, Rad: np.ndarray,
                        T0: float) -> np.ndarray:
    """Trajectoire libre (free-run) : T_int(t+1)=T_int(t)+a·(Text-T_int)+b·Rad+c.

    Aucune production de froid (Q_froid = 0) pendant la calibration (§4.6).
    """
    n = len(Text)
    T = np.empty(n)
    T[0] = T0
    for k in range(n - 1):
        T[k + 1] = T[k] + a * (Text[k] - T[k]) + b * Rad[k] + c
    return T


def _indicateurs(sim: np.ndarray, mesure: np.ndarray) -> dict:
    err = sim - mesure
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(np.mean(np.abs(err)))
    biais = float(np.mean(err))
    ss_res = np.sum((mesure - sim) ** 2)
    ss_tot = np.sum((mesure - np.mean(mesure)) ** 2)
    r2 = float(1.0 - ss_res / ss_tot)
    return {"rmse": rmse, "mae": mae, "biais": biais, "r2": r2}


def identifier_one_step(d: DonneesCalibration) -> ModeleRC:
    """Identification par moindres carrés à un pas (§4.7).

    On régresse l'incrément mesuré ΔT_int(t) = T_int(t+1) - T_int(t) sur
    les variables [ (T_ext - T_int), Rad, 1 ]. Solution analytique.
    Reproduit les coefficients des parties 2 et 3.
    """
    Ti, Te, Ra = d.Tint, d.Text, d.Rad
    y = Ti[1:] - Ti[:-1]
    X = np.column_stack([Te[:-1] - Ti[:-1], Ra[:-1], np.ones(len(y))])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b, c = map(float, coef)
    sim = simuler_trajectoire(a, b, c, Te, Ra, Ti[0])
    ind = _indicateurs(sim, Ti)
    return ModeleRC(a=a, b=b, c=c, methode="one_step", tau_h=1.0 / a,
                    simulation=sim, **ind)


def identifier_free_run(d: DonneesCalibration,
                        p0: tuple[float, float, float] | None = None) -> ModeleRC:
    """Identification par minimisation de l'erreur sur la trajectoire (§4.7).

    Minimise le RMSE entre la trajectoire libre simulée et la mesure sur les
    960 heures. Reproduit les coefficients de la partie 1 (référence V3).
    """
    Ti, Te, Ra = d.Tint, d.Text, d.Rad
    if p0 is None:
        # départ = solution one-step, robuste
        p0 = tuple(identifier_one_step(d).as_dict().values())

    def cout(p):
        a, b, c = p
        sim = simuler_trajectoire(a, b, c, Te, Ra, Ti[0])
        return np.sqrt(np.mean((sim - Ti) ** 2))

    res = minimize(cout, np.asarray(p0), method="Nelder-Mead",
                   options={"xatol": 1e-8, "fatol": 1e-7, "maxiter": 20000})
    a, b, c = map(float, res.x)
    sim = simuler_trajectoire(a, b, c, Te, Ra, Ti[0])
    ind = _indicateurs(sim, Ti)
    return ModeleRC(a=a, b=b, c=c, methode="free_run", tau_h=1.0 / a,
                    simulation=sim, **ind)


# --------------------------------------------------------------------------
# §4.9 — Passage des coefficients apparents vers des grandeurs physiques
# --------------------------------------------------------------------------
def conversion_grandeurs_physiques(modele: ModeleRC,
                                   rad_reference: float = 1.0,
                                   surface_m2: float = config.SURFACE_TOTALE_M2
                                   ) -> pd.DataFrame:
    """Table de conversion pour les capacités surfaciques 80/120/165 Wh/m².K.

    Formules (Annexe A) :
        C   = Surface × capacité surfacique            [MWh/K]
        UA  = a × C                                    [kW/K]  (×1000)
        Psol/W-m² = b × C                              [kW par W/m²]
        Pres = c × C                                   [kW]
    """
    lignes = []
    for cap in config.CAPACITES_SURFACIQUES_SENSIBILITE:
        C = config.capacite_totale_MWh_par_K(cap, surface_m2)     # MWh/K
        UA = modele.a * C * 1000.0                                 # kW/K
        sens_sol = modele.b * C * 1000.0                           # kW par (W/m²)
        pres = modele.c * C * 1000.0                               # kW
        lignes.append({
            "Capacité surfacique (Wh/m².K)": cap,
            "Capacité totale C (MWh/K)": C,
            "UA apparent (kW/K)": UA,
            "Sensibilité solaire (kW par W/m²)": sens_sol,
            "Terme résiduel (kW)": pres,
        })
    return pd.DataFrame(lignes).set_index("Capacité surfacique (Wh/m².K)")


def modele_pour_simulation(d: DonneesCalibration, cfg: config.ConfigModele) -> ModeleRC:
    """Renvoie le modèle utilisé par les simulations de puissance."""
    if cfg.coeffs_simulation == "free_run":
        return identifier_free_run(d)
    return identifier_one_step(d)
