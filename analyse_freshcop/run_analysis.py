#!/usr/bin/env python3
"""Exécute l'ensemble des analyses du Chapitre 4 FRESHCOP consolidé (V3).

Reproduit, dans l'ordre du document, toutes les analyses et tous les calculs :
    Partie 1  calibration du modèle thermique dynamique (§4.1-4.10) ;
    Partie 2  simulation sans rafraîchissement, projection 2050 (§4.2.x) ;
    Partie 3  dimensionnement dynamique et marges 2 / 2,5 / 3 MW (§4.3.x) ;
    Partie 4  conclusion consolidée de dimensionnement (§4.4.x).

Le script imprime chaque tableau, compare les résultats calculés aux valeurs
documentées (colonne « écart »), génère les figures et exporte les tableaux
en CSV dans le dossier de sorties.

Usage
-----
    python run_analysis.py [--csv CHEMIN] [--sorties DOSSIER]
                           [--coeffs {one_step,free_run}] [--sans-figures]
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

# Permet d'exécuter le script depuis n'importe quel dossier
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from freshcop import config, data, stats, calibration, simulation, sizing  # noqa: E402


LARGEUR = 78


def titre(txt: str, char: str = "=") -> None:
    print("\n" + char * LARGEUR)
    print(txt)
    print(char * LARGEUR)


def sous_titre(txt: str) -> None:
    print("\n--- " + txt + " " + "-" * max(0, LARGEUR - len(txt) - 5))


def afficher(df: pd.DataFrame, floatfmt: str = "%.3f") -> None:
    with pd.option_context("display.max_columns", None,
                           "display.width", 200,
                           "display.float_format", lambda v: floatfmt % v):
        print(df.to_string())


def ecart(calcule: float, doc: float) -> str:
    if doc == 0:
        return f"{calcule:+.3f} (doc 0)"
    return f"calc {calcule:.3f} / doc {doc:.3f} (Δ {calcule - doc:+.3f})"


def exporter(df: pd.DataFrame, dossier: str, nom: str) -> None:
    os.makedirs(dossier, exist_ok=True)
    df.to_csv(os.path.join(dossier, nom), float_format="%.4f")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=None, help="chemin du CSV de mesures")
    p.add_argument("--sorties", default=None, help="dossier des sorties")
    p.add_argument("--coeffs", choices=("one_step", "free_run"), default="one_step",
                   help="jeu de coefficients pour les simulations de puissance")
    p.add_argument("--sans-figures", action="store_true", help="ne pas générer les figures")
    args = p.parse_args(argv)

    ici = os.path.dirname(os.path.abspath(__file__))
    racine = os.path.dirname(ici)
    cfg = config.ConfigModele(
        chemin_csv=args.csv or os.path.join(racine, "T appart mai - jin 26.csv"),
        dossier_sorties=args.sorties or os.path.join(ici, "sorties"),
        coeffs_simulation=args.coeffs,
        generer_figures=not args.sans_figures,
    )
    dossier_csv = os.path.join(cfg.dossier_sorties, "tableaux")

    # ======================================================================
    titre("DONNÉES — lecture et cadrage du CSV (§4.2)")
    d = data.preparer(cfg.chemin_csv)
    print(f"Fichier            : {cfg.chemin_csv}")
    print(f"Mesures retenues   : {len(d)} heures "
          f"(du {d.temps.iloc[0]} au {d.temps.iloc[-1]})")
    print(f"Surface représentative : {config.SURFACE_TOTALE_M2:.0f} m² "
          f"({config.NB_LOGEMENTS} logements × {config.SURFACE_MOY_LOGEMENT_M2:.0f} m²)")
    print(f"T ext. moyenne = {d.Text.mean():.2f} °C   "
          f"T int. moyenne AB/CD = {d.Tint.mean():.2f} °C   "
          f"écart = {d.Tint.mean() - d.Text.mean():.2f} °C")

    # ======================================================================
    titre("PARTIE 1 — Calibration du modèle thermique dynamique (§4.1-4.10)")

    sous_titre("§4.3 Statistiques descriptives")
    stat = stats.statistiques_descriptives(d)
    afficher(stat, "%.2f")
    exporter(stat, dossier_csv, "p1_statistiques.csv")

    sous_titre("§4.3 Heures de dépassement et degrés-heures (T int. AB/CD)")
    dh = stats.degres_heures(d.Tint)
    afficher(dh, "%.1f")
    exporter(dh, dossier_csv, "p1_degres_heures.csv")

    sous_titre("§4.6-4.7 Identification du modèle RC")
    modele_p1 = calibration.identifier_free_run(d)     # référence partie 1
    modele_os = calibration.identifier_one_step(d)     # parties 2/3
    print("Forme : T_int(t+1) = T_int(t) + a·[T_ext−T_int] + b·Rad + c\n")
    print("  [free_run — référence Partie 1]")
    print(f"    a={modele_p1.a:.6f}  b={modele_p1.b:.8f}  c={modele_p1.c:.5f}")
    print(f"    tau = {modele_p1.tau_h:.0f} h ({modele_p1.tau_jours:.1f} j)   "
          f"RMSE={modele_p1.rmse:.2f}  MAE={modele_p1.mae:.2f}  "
          f"biais={modele_p1.biais:+.2f}  R²={modele_p1.r2:.2f}")
    v = config.VALIDATION_PARTIE1
    print(f"    doc Partie 1 : a=0.003035 b=0.00012597 c=-0.01829 | "
          f"tau={v['tau_h']:.0f} RMSE={v['rmse']} R²={v['r2']}")
    print("\n  [one_step — Parties 2 & 3]")
    print(f"    a={modele_os.a:.6f}  b={modele_os.b:.8f}  c={modele_os.c:.5f}")
    print(f"    tau = {modele_os.tau_h:.0f} h ({modele_os.tau_jours:.1f} j)   "
          f"RMSE={modele_os.rmse:.2f}  R²={modele_os.r2:.2f}")
    v = config.VALIDATION_PARTIE23
    print(f"    doc Parties 2/3 : a=0.00363 b=0.0001462 c=-0.0270 | "
          f"tau={v['tau_h']:.0f} RMSE={v['rmse']} R²={v['r2']}")

    sous_titre("§4.8 Déphasage et inertie (corrélation croisée)")
    dep = stats.dephasage(d)
    print(f"  Mémoire lente (brute)   : lag = {dep.lag_brut_h} h "
          f"(R = {dep.r_brut:.2f})   [doc ≈ 51 h, R = 0,81]")
    print(f"  Réponse journalière     : lag = {dep.lag_detendance_h} h "
          f"(R = {dep.r_detendance:.2f})   [doc ≈ 3 h, R = 0,85]")

    sous_titre("§4.8 Refroidissement nocturne (20 h → 6 h)")
    rn = stats.refroidissement_nocturne(d)
    print(f"  Baisse extérieure disponible : {rn.baisse_ext_moy:.1f} °C   [doc ≈ 8,4]")
    print(f"  Baisse intérieure observée   : {rn.baisse_int_moy:.1f} °C   [doc ≈ 0,6]")
    print(f"  Taux de récupération         : {100 * rn.taux_recuperation:.0f} %")

    sous_titre("§4.9 Conversion coefficients apparents → grandeurs physiques")
    conv = calibration.conversion_grandeurs_physiques(modele_os)
    afficher(conv, "%.2f")
    exporter(conv, dossier_csv, "p1_conversion_physique.csv")

    # Modèle retenu pour les simulations de puissance
    modele_sim = modele_os if cfg.coeffs_simulation == "one_step" else modele_p1

    # ======================================================================
    titre("PARTIE 2 — Simulation sans rafraîchissement, projection 2050 (§4.2.x)")

    sous_titre("§4.2.2 Températures intérieures libres simulées")
    tl = simulation.synthese_temperatures_libres(modele_sim, d)
    afficher(tl, "%.2f")
    exporter(tl, dossier_csv, "p2_temperatures_libres.csv")

    sous_titre("§4.2.3 Dépassement des cibles en 2050 (par zone)")
    dc = simulation.depassement_cibles(modele_sim, d, delta_T=2.2, mode="reactif")
    afficher(dc, "%.2f")
    exporter(dc, dossier_csv, "p2_depassement_cibles_2050.csv")

    sous_titre("§4.2.8 Métrique V3 — nuits chaudes (22 h → 7 h, ≥ 6 h)")
    nc = simulation.synthese_nuits_chaudes(modele_sim, d)
    afficher(nc, "%.1f")
    exporter(nc, dossier_csv, "p2_nuits_chaudes.csv")

    sous_titre("§4.2.9 Sensibilité pilotage des chambres (nuit seule vs 24h/24)")
    sc = sizing.sensibilite_chambres(modele_sim, d, delta_T=2.2)
    afficher(sc, "%.2f")
    exporter(sc, dossier_csv, "p2_sensibilite_chambres.csv")

    # ======================================================================
    titre("PARTIE 3 — Dimensionnement dynamique et marges (§4.3.x)")

    sous_titre("§4.3.6 Tableau de dimensionnement par scénario climatique")
    dim, resultats = sizing.tableau_dimensionnement(modele_sim, d, mode="reactif")
    afficher(dim, "%.2f")
    exporter(dim, dossier_csv, "p3_dimensionnement.csv")
    print("  [doc 2050 : pic 2,65 MW · énergie 73,8 MWh · 236 h actives]")

    sous_titre("§4.3.7 Marges de puissance 2 / 2,5 / 3 MW (pilotage réactif)")
    marges = sizing.tableau_marges(resultats)
    afficher(marges, "%.2f")
    exporter(marges, dossier_csv, "p3_marges.csv")
    print("  [doc 2050 : −0,65 / −0,15 / +0,35 MW]")

    sous_titre("§4.3.8 Heures de saturation")
    satur = sizing.tableau_saturation(resultats)
    afficher(satur, "%.0f")
    exporter(satur, dossier_csv, "p3_saturation.csv")
    print("  [doc 2050 : 3 h / 1 h / 0 h]")

    ref = resultats[[n for n in resultats if n.startswith(config.SCENARIO_CENTRAL)][0]]

    sous_titre("§4.3.9 Contribution des zones au besoin de froid (2050)")
    cz = sizing.contribution_zones(ref)
    afficher(cz, "%.2f")
    exporter(cz, dossier_csv, "p3_contribution_zones.csv")
    print("  [doc : chambres ≈ 42,1 % pour 33 % de surface]")

    sous_titre("§4.3.10 Effet du vitrage sur le besoin (2050)")
    cv = sizing.contribution_vitrage(ref)
    afficher(cv, "%.2f")
    exporter(cv, dossier_csv, "p3_contribution_vitrage.csv")

    sous_titre("§4.3.11 Sensibilité de dimensionnement (capacité × prudence)")
    sd = sizing.sensibilite_dimensionnement(modele_sim, d, delta_T=2.2)
    afficher(sd, "%.2f")
    exporter(sd.reset_index(), dossier_csv, "p3_sensibilite_dimensionnement.csv")

    sous_titre("§4.3.12 Effet du pilotage (réactif vs anticipatif) — 2050")
    cp = sizing.comparaison_pilotage(modele_sim, d, delta_T=2.2)
    afficher(cp, "%.2f")
    exporter(cp, dossier_csv, "p3_comparaison_pilotage.csv")

    # ======================================================================
    titre("PARTIE 4 — Conclusion consolidée de dimensionnement V3 (§4.4)")
    dec = sizing.tableau_decision(resultats)
    afficher(dec, "%.2f")
    exporter(dec, dossier_csv, "p4_decision.csv")
    pic_ref = ref.pic_MW
    print(f"\n  Pic non contraint 2050 (pilotage réactif) : {pic_ref:.2f} MW")
    print("  Lecture V3 :")
    print("    • 2 MW   → insuffisant en pilotage réactif (saturation nocturne).")
    print("    • 2,5 MW → limite : proche du pic, sans réserve robuste.")
    print("    • 3 MW   → enveloppe cohérente : marge faible mais positive, "
          "0 h de saturation.")
    print("  Le chiffre 1,19 MW (lecture moyenne) est écarté au profit du pic "
          "réactif dimensionnant.")

    # ======================================================================
    if cfg.generer_figures:
        titre("FIGURES")
        try:
            from freshcop import figures
            chemins = figures.generer_toutes(modele_p1, modele_sim, d, resultats,
                                             os.path.join(cfg.dossier_sorties, "figures"))
            for c in chemins:
                print("  ✓ " + os.path.relpath(c, ici))
        except Exception as exc:  # matplotlib absent, etc.
            print(f"  (figures non générées : {exc})")

    titre("TERMINÉ")
    print(f"Tableaux CSV : {os.path.relpath(dossier_csv, ici)}/")
    if cfg.generer_figures:
        print(f"Figures      : {os.path.relpath(os.path.join(cfg.dossier_sorties, 'figures'), ici)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
