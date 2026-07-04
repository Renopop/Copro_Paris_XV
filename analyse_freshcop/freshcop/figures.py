"""Génération des figures du Chapitre 4 (matplotlib, backend non interactif)."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # pas d'affichage interactif
import matplotlib.pyplot as plt
import numpy as np

from . import config
from .calibration import ModeleRC, conversion_grandeurs_physiques
from .data import DonneesCalibration
from .simulation import temperature_libre
from .sizing import courbe_duree_charge, puissance_froid


def _save(fig, dossier, nom):
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    fig.savefig(chemin, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return chemin


def figure_mesures(d: DonneesCalibration, dossier: str) -> str:
    """Fig. 1 — mesures horaires de température après arrêt du chauffage."""
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(d.temps, d.Text, lw=0.8, label="Extérieure", color="#1f77b4")
    ax.plot(d.temps, d.Tint, lw=1.0, label="Intérieure moyenne AB/CD", color="#d62728")
    ax.set_ylabel("Température (°C)")
    ax.set_title("Mesures horaires — période post-chauffage (22/05 → 30/06/2026)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    return _save(fig, dossier, "fig01_mesures_temperatures.png")


def figure_calibration(modele: ModeleRC, d: DonneesCalibration, dossier: str) -> str:
    """Fig. 4/5 — température mesurée vs simulée + erreur horaire."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(d.temps, d.Tint, lw=1.0, label="Mesurée", color="#d62728")
    ax1.plot(d.temps, modele.simulation, lw=1.0, ls="--",
             label=f"Simulée RC ({modele.methode})", color="#1f77b4")
    ax1.set_ylabel("T intérieure (°C)")
    ax1.set_title(f"Calibration RC — RMSE={modele.rmse:.2f} °C  R²={modele.r2:.2f}  "
                  f"τ={modele.tau_h:.0f} h")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)
    ax2.plot(d.temps, modele.simulation - d.Tint, lw=0.7, color="#555")
    ax2.axhline(0, color="k", lw=0.6)
    ax2.set_ylabel("Erreur (°C)")
    ax2.grid(alpha=0.3)
    return _save(fig, dossier, "fig04_calibration.png")


def figure_temperatures_libres(modele: ModeleRC, d: DonneesCalibration, dossier: str) -> str:
    """Fig. 2 (partie 2) — températures libres 2026 / 2050 / 2100."""
    fig, ax = plt.subplots(figsize=(11, 4))
    couleurs = {"2026 sans froid": "#2ca02c", "2050 +2,2 °C sans froid": "#ff7f0e",
                "2100 +3,2 °C sans froid": "#d62728"}
    for sc in config.SCENARIOS_TEMPERATURE:
        T = temperature_libre(modele, d, sc.delta_T)
        ax.plot(d.temps, T, lw=0.9, label=sc.nom,
                color=couleurs.get(sc.nom))
    ax.axhline(26, color="k", ls=":", lw=0.8, label="Cible séjour 26 °C")
    ax.axhline(24, color="gray", ls=":", lw=0.8, label="Cible chambres 24 °C")
    ax.set_ylabel("T intérieure libre (°C)")
    ax.set_title("Températures intérieures simulées sans rafraîchissement")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    ax.grid(alpha=0.3)
    return _save(fig, dossier, "fig02_temperatures_libres.png")


def figure_puissance_horaire(modele: ModeleRC, d: DonneesCalibration, dossier: str) -> str:
    """Fig. 13 — puissance horaire 2050 + lignes de capacité 2 / 2,5 / 3 MW."""
    r = puissance_froid(modele, d, 2.2, mode="reactif")
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(d.temps, r.puissance, lw=0.8, color="#1f77b4")
    for cap, col in zip(config.CAPACITES_INSTALLEES_MW, ("#2ca02c", "#ff7f0e", "#d62728")):
        ax.axhline(cap, ls="--", lw=1.0, color=col, label=f"{cap:g} MW")
    ax.set_ylabel("Puissance froid appelée (MW)")
    ax.set_title(f"Puissance horaire 2050 (pilotage réactif) — pic {r.pic_MW:.2f} MW")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    return _save(fig, dossier, "fig13_puissance_horaire_2050.png")


def figure_courbe_duree(modele: ModeleRC, d: DonneesCalibration, dossier: str) -> str:
    """Fig. 12 — courbe de durée de charge 2050 réactif vs anticipatif."""
    reac = courbe_duree_charge(modele, d, 2.2, "reactif")
    anti = courbe_duree_charge(modele, d, 2.2, "anticipatif")
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(reac, lw=1.2, label=f"Réactif (pic {reac.max():.2f} MW)", color="#d62728")
    ax.plot(anti, lw=1.2, label=f"Anticipatif (pic {anti.max():.2f} MW)", color="#1f77b4")
    for cap in config.CAPACITES_INSTALLEES_MW:
        ax.axhline(cap, ls=":", lw=0.7, color="gray")
    ax.set_xlabel("Heures classées par puissance décroissante")
    ax.set_ylabel("Puissance (MW)")
    ax.set_title("Courbe de durée de charge — projection 2050")
    ax.legend()
    ax.grid(alpha=0.3)
    return _save(fig, dossier, "fig12_courbe_duree_charge.png")


def figure_marges(resultats: dict, dossier: str) -> str:
    """Fig. 14 — marges de puissance selon les scénarios climatiques."""
    noms = list(resultats.keys())
    pics = np.array([resultats[n].pic_MW for n in noms])
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(noms))
    w = 0.25
    for i, cap in enumerate(config.CAPACITES_INSTALLEES_MW):
        ax.bar(x + (i - 1) * w, cap - pics, w, label=f"{cap:g} MW")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(noms, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Marge = capacité − pic (MW)")
    ax.set_title("Marges de puissance (pilotage réactif)")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, dossier, "fig14_marges_puissance.png")


def figure_sensibilite_capacite(modele: ModeleRC, d: DonneesCalibration, dossier: str) -> str:
    """Fig. 18 — sensibilité du pic 2050 à la capacité thermique."""
    caps = config.CAPACITES_SURFACIQUES_SENSIBILITE
    pics = [puissance_froid(modele, d, 2.2, capacite_surfacique=c).pic_MW for c in caps]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(caps, pics, "o-", color="#1f77b4")
    for cap in config.CAPACITES_INSTALLEES_MW:
        ax.axhline(cap, ls=":", lw=0.7, color="gray")
        ax.text(caps[0], cap, f"{cap:g} MW", fontsize=8, va="bottom")
    ax.set_xlabel("Capacité thermique effective (Wh/m².K)")
    ax.set_ylabel("Pic de puissance 2050 (MW)")
    ax.set_title("Sensibilité du pic 2050 à la capacité thermique")
    ax.grid(alpha=0.3)
    return _save(fig, dossier, "fig18_sensibilite_capacite.png")


def generer_toutes(modele_p1: ModeleRC, modele_sim: ModeleRC,
                   d: DonneesCalibration, resultats: dict, dossier: str) -> list[str]:
    """Génère l'ensemble des figures et renvoie la liste des chemins."""
    return [
        figure_mesures(d, dossier),
        figure_calibration(modele_p1, d, dossier),
        figure_temperatures_libres(modele_sim, d, dossier),
        figure_puissance_horaire(modele_sim, d, dossier),
        figure_courbe_duree(modele_sim, d, dossier),
        figure_marges(resultats, dossier),
        figure_sensibilite_capacite(modele_sim, d, dossier),
    ]
