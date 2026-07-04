#!/usr/bin/env python3
"""Module interactif FRESHCOP — toutes les hypothèses modifiables en direct.

Interface Streamlit permettant de modifier chaque hypothèse du Chapitre 4
(répartition des vitrages, consignes et parts de surface par zone, capacité
thermique, scénarios climatiques, pilotage, capacités installées...) et de
voir se recalculer instantanément le dimensionnement, les marges, la
saturation et les indicateurs de confort.

Lancement :
    cd analyse_freshcop
    pip install -r requirements.txt
    streamlit run app_interactif.py
"""

from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from freshcop import data, calibration, interactif
from freshcop.interactif import Hypotheses, ZoneH

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DEFAUT = os.path.join(RACINE, "T appart mai - jin 26.csv")

st.set_page_config(page_title="FRESHCOP — Modèle interactif", layout="wide",
                   page_icon="❄️")


# --------------------------------------------------------------------------
# Chargement & calibration (mis en cache : ne dépendent que du CSV)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="Lecture du CSV…")
def _charger(chemin: str):
    return data.preparer(chemin)


@st.cache_data(show_spinner="Calibration du modèle RC…")
def _calibrer(chemin: str):
    d = _charger(chemin)
    return calibration.identifier_free_run(d), calibration.identifier_one_step(d)


# --------------------------------------------------------------------------
# Barre latérale : toutes les hypothèses
# --------------------------------------------------------------------------
def barre_laterale() -> tuple[Hypotheses, str]:
    st.sidebar.title("❄️ Hypothèses")
    chemin = st.sidebar.text_input("Fichier CSV de mesures", CSV_DEFAUT)

    if st.sidebar.button("↺ Réinitialiser (valeurs du document)"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    h = Hypotheses()

    with st.sidebar.expander("🏢 Résidence", expanded=False):
        h.nb_logements = st.number_input("Nombre de logements", 1, 5000, 440, 10)
        h.surface_moy_logement = st.number_input(
            "Surface moyenne / logement (m²)", 10.0, 300.0, 80.0, 5.0)
        st.caption(f"Surface totale représentative : **{h.surface_totale:,.0f} m²**")

    with st.sidebar.expander("🔧 Calibration & capacité thermique", expanded=False):
        h.coeffs = st.radio(
            "Jeu de coefficients", ["one_step", "free_run"],
            format_func=lambda x: {"one_step": "one-step (Parties 2/3)",
                                   "free_run": "free-run (Partie 1)"}[x])
        h.capacite_surfacique = st.slider(
            "Capacité thermique effective (Wh/m².K)", 60.0, 200.0, 120.0, 5.0,
            help="Convertit les degrés en puissance (§4.9). Réf. document : 120.")

    with st.sidebar.expander("🪟 Vitrage", expanded=True):
        pct_simple = st.slider("Part simple vitrage (%)", 0, 100, 60, 5)
        h.part_simple = pct_simple / 100.0
        h.facteur_simple = st.slider("Facteur simple vitrage", 0.8, 1.6, 1.15, 0.01)
        h.facteur_double = st.slider("Facteur double vitrage", 0.4, 1.2, 0.775, 0.005)
        st.caption(f"Double vitrage : **{100 - pct_simple} %** · "
                   f"facteur moyen pondéré : **{h.facteur_vitrage_moyen:.3f}**")
        if abs(h.facteur_vitrage_moyen - 1.0) > 0.02:
            st.warning("Le facteur moyen s'écarte de 1,00 : le comportement "
                       "moyen ne sera plus celui calibré sur le CSV.")

    with st.sidebar.expander("🛏️ Zones & consignes", expanded=True):
        zones = []
        for z0 in Hypotheses().zones:
            st.markdown(f"**{z0.nom}**")
            c1, c2, c3 = st.columns(3)
            part = c1.number_input("Part surf.", 0.0, 1.0, z0.part_surface, 0.01,
                                   key=f"part_{z0.nom}")
            cj = c2.number_input("Consigne jour", 18.0, 30.0, z0.consigne_jour, 0.5,
                                 key=f"cj_{z0.nom}")
            cn = c3.number_input("Consigne nuit", 18.0, 30.0, z0.consigne_nuit, 0.5,
                                 key=f"cn_{z0.nom}")
            zones.append(ZoneH(z0.nom, part, cj, cn))
        h.zones = zones
        somme = sum(z.part_surface for z in zones)
        (st.caption if abs(somme - 1.0) < 1e-6 else st.warning)(
            f"Somme des parts de surface : {somme:.2f} (cible 1,00)")

    with st.sidebar.expander("🎛️ Pilotage", expanded=False):
        h.mode = st.radio(
            "Mode de pilotage", ["reactif", "anticipatif"],
            format_func=lambda x: {"reactif": "Réactif (dimensionne la puissance)",
                                   "anticipatif": "Anticipatif (écrête les pointes)"}[x])
        c1, c2 = st.columns(2)
        h.nuit_debut_h = c1.number_input("Début nuit (h)", 0, 23, 20)
        h.nuit_fin_h = c2.number_input("Fin nuit (h)", 0, 23, 8)

    with st.sidebar.expander("🌡️ Scénarios climatiques", expanded=False):
        scen = []
        for nom, dt in Hypotheses().scenarios:
            v = st.slider(nom, 0.0, 6.0, float(dt), 0.1, key=f"sc_{nom}")
            scen.append([nom, v])
        h.scenarios = scen
        noms = [s[0] for s in scen]
        focus_nom = st.selectbox("Scénario mis en avant", noms,
                                 index=min(2, len(noms) - 1))
        h.delta_focus = dict((n, v) for n, v in scen)[focus_nom]
        st.session_state["_focus_nom"] = focus_nom

    with st.sidebar.expander("⚡ Capacités & robustesse", expanded=False):
        caps = st.text_input("Capacités installées (MW, séparées par virgule)",
                             "2, 2.5, 3")
        try:
            h.capacites_installees = tuple(sorted(
                float(x.strip().replace(",", ".")) for x in caps.split(",") if x.strip()))
        except ValueError:
            st.error("Format invalide — ex. : 2, 2.5, 3")
        seuils = st.text_input("Seuils nuits chaudes (°C)", "26, 28, 30")
        try:
            h.seuils_nuits = tuple(
                float(x.strip().replace(",", ".")) for x in seuils.split(",") if x.strip())
        except ValueError:
            st.error("Format invalide — ex. : 26, 28, 30")

    return h, chemin


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def fig_puissance(res, h) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.plot(res["temps"], res["Q_focus"], lw=0.7, color="#1f77b4")
    for cap, col in zip(h.capacites_installees,
                        plt.cm.autumn(np.linspace(0, 0.7, len(h.capacites_installees)))):
        ax.axhline(cap, ls="--", lw=1.0, color=col, label=f"{cap:g} MW")
    ax.set_ylabel("Puissance froid (MW)")
    ax.set_title(f"Puissance horaire appelée — pic {res['focus'].pic_MW:.2f} MW")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    return fig


def fig_duree(res, h) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.plot(res["courbe_duree_reactif"], lw=1.3,
            label=f"Réactif (pic {res['courbe_duree_reactif'].max():.2f})", color="#d62728")
    ax.plot(res["courbe_duree_anticipatif"], lw=1.3,
            label=f"Anticipatif (pic {res['courbe_duree_anticipatif'].max():.2f})",
            color="#1f77b4")
    for cap in h.capacites_installees:
        ax.axhline(cap, ls=":", lw=0.7, color="gray")
    ax.set_xlabel("Heures classées")
    ax.set_ylabel("Puissance (MW)")
    ax.set_title("Courbe de durée de charge")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return fig


# --------------------------------------------------------------------------
# Application principale
# --------------------------------------------------------------------------
def main():
    st.title("❄️ FRESHCOP — Modèle thermique interactif")
    st.caption("Chapitre 4 consolidé V3 · toutes les hypothèses sont modifiables "
               "dans la barre latérale ← · recalcul en direct.")

    h, chemin = barre_laterale()

    if not os.path.exists(chemin):
        st.error(f"Fichier introuvable : {chemin}")
        st.stop()

    d = _charger(chemin)
    modele_p1, modele_os = _calibrer(chemin)
    res = interactif.calculer_tout(h, d, modele_p1, modele_os)
    focus = res["focus"]
    focus_nom = st.session_state.get("_focus_nom", "scénario retenu")

    # --- Bandeau d'indicateurs clés ---
    reco = res["capacite_recommandee"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(f"Pic non contraint ({focus_nom})", f"{focus.pic_MW:.2f} MW")
    c2.metric("Énergie froide période", f"{focus.energie_MWh:.1f} MWh")
    marge3 = (h.capacites_installees[-1] - focus.pic_MW) if h.capacites_installees else float("nan")
    c3.metric(f"Marge {h.capacites_installees[-1]:g} MW" if h.capacites_installees else "Marge",
              f"{marge3:+.2f} MW")
    c4.metric("Part chambres", f"{100 * focus.energie_zone['Chambres'] / focus.energie_MWh:.1f} %"
              if focus.energie_MWh else "—")
    c5.metric("Capacité recommandée",
              f"{reco:g} MW" if reco else "> capacités testées")

    st.divider()

    g, dr = st.columns([2, 1])
    g.pyplot(fig_puissance(res, h))
    dr.pyplot(fig_duree(res, h))

    # --- Onglets détaillés ---
    o1, o2, o3, o4, o5 = st.tabs(
        ["📏 Dimensionnement", "🎯 Marges & saturation", "🧩 Contributions",
         "🌡️ Confort", "🔬 Calibration & sensibilités"])

    with o1:
        st.subheader("Dimensionnement par scénario climatique (§4.3.6)")
        st.dataframe(_fmt(res["dimensionnement"]), width="stretch")
        st.subheader("Décision consolidée sur le scénario retenu (§4.4)")
        st.dataframe(_fmt(res["decision"]), width="stretch")

    with o2:
        st.subheader("Marges de puissance (§4.3.7)")
        st.dataframe(_fmt(res["marges"]), width="stretch")
        st.subheader("Heures de saturation (§4.3.8)")
        st.dataframe(_fmt(res["saturation"], "%.0f"), width="stretch")

    with o3:
        cza, czb = st.columns(2)
        cza.subheader("Contribution des zones (§4.3.9)")
        cza.dataframe(_fmt(res["contribution_zones"]), width="stretch")
        czb.subheader("Effet du vitrage (§4.3.10)")
        czb.dataframe(_fmt(res["contribution_vitrage"]), width="stretch")
        st.subheader("Effet du pilotage réactif vs anticipatif (§4.3.12)")
        st.dataframe(_fmt(res["comparaison_pilotage"]), width="stretch")

    with o4:
        st.subheader("Températures intérieures libres (§4.2.2)")
        st.dataframe(_fmt(res["temperatures_libres"], "%.2f"), width="stretch")
        st.subheader("Dépassement des cibles par zone (§4.2.3)")
        st.dataframe(_fmt(res["depassement"], "%.2f"), width="stretch")
        st.subheader("Nuits chaudes — métrique V3 (§4.2.8)")
        st.dataframe(_fmt(res["nuits_chaudes"], "%.1f"), width="stretch")

    with o5:
        m = res["modele"]
        st.write(f"**Modèle retenu : {m.methode}** — "
                 f"a={m.a:.5f}, b={m.b:.7f}, c={m.c:.5f} · "
                 f"τ={m.tau_h:.0f} h · RMSE={m.rmse:.2f} °C · R²={m.r2:.2f}")
        st.subheader("Conversion vers grandeurs physiques (§4.9)")
        st.dataframe(_fmt(res["conversion"], "%.2f"), width="stretch")
        st.subheader("Sensibilité du dimensionnement (capacité × prudence) (§4.3.11)")
        st.dataframe(_fmt(res["sensibilite_dimensionnement"], "%.2f"),
                     width="stretch")
        st.subheader("Sensibilité au pilotage des chambres (§4.2.9)")
        st.dataframe(_fmt(res["sensibilite_chambres"], "%.2f"), width="stretch")

    st.divider()
    st.caption("Pré-dimensionnement — non substituable à une étude thermique "
               "détaillée logement par logement (§4.10).")


def _fmt(df: pd.DataFrame, fmt: str = "%.2f"):
    return df.style.format(fmt, na_rep="—")


if __name__ == "__main__":
    main()
