"""Tests de non-régression : les calculs doivent reproduire les valeurs du
document ``FRESHCOP_Chapitre4_Consolide_Corrections_V3_Recentrage_1_2_3.docx``.

Lancer avec :  pytest -q   (depuis le dossier analyse_freshcop)
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from freshcop import config, data, stats, calibration, simulation, sizing

CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "T appart mai - jin 26.csv")


@pytest.fixture(scope="module")
def d():
    return data.preparer(CSV)


@pytest.fixture(scope="module")
def modele(d):
    return calibration.identifier_one_step(d)


# ------------------------------------------------------------------ Partie 1
def test_periode_960_heures(d):
    assert len(d) == 960


def test_moyennes_mesurees(d):
    assert d.Text.mean() == pytest.approx(23.11, abs=0.01)
    assert d.Tint.mean() == pytest.approx(26.21, abs=0.01)
    assert d.Tint_AB.mean() == pytest.approx(26.40, abs=0.01)
    assert d.Tint_CD.mean() == pytest.approx(26.03, abs=0.01)


def test_degres_heures(d):
    dh = stats.degres_heures(d.Tint)
    assert int(dh.loc[">24 °C", "Heures"]) == 657
    assert dh.loc[">24 °C", "Degrés-heures"] == pytest.approx(2477, abs=1)
    assert dh.loc[">26 °C", "Degrés-heures"] == pytest.approx(1349, abs=1)


def test_calibration_free_run(d):
    m = calibration.identifier_free_run(d)
    assert m.a == pytest.approx(0.003035, abs=5e-5)   # doc Partie 1
    assert m.tau_h == pytest.approx(330, abs=5)
    assert m.rmse == pytest.approx(1.32, abs=0.02)
    assert m.r2 == pytest.approx(0.81, abs=0.02)


def test_calibration_one_step(modele):
    assert modele.a == pytest.approx(0.00363, abs=5e-5)  # doc Parties 2/3
    assert modele.tau_h == pytest.approx(275, abs=3)
    assert modele.r2 == pytest.approx(0.67, abs=0.02)


def test_dephasage(d):
    dep = stats.dephasage(d)
    assert dep.lag_brut_h == 51
    assert dep.lag_detendance_h == 3


def test_refroidissement_nocturne(d):
    rn = stats.refroidissement_nocturne(d)
    assert rn.baisse_ext_moy == pytest.approx(8.4, abs=0.3)
    assert rn.baisse_int_moy == pytest.approx(0.6, abs=0.3)


def test_conversion_physique(modele):
    conv = calibration.conversion_grandeurs_physiques(modele)
    assert conv.loc[120.0, "Capacité totale C (MWh/K)"] == pytest.approx(4.22, abs=0.01)


# ------------------------------------------------------------------ Partie 2
def test_temperatures_libres(modele, d):
    tl = simulation.synthese_temperatures_libres(modele, d)
    assert tl.loc["2026 sans froid", "Moyenne °C"] == pytest.approx(25.17, abs=0.05)
    assert tl.loc["2050 +2,2 °C sans froid", "Moyenne °C"] == pytest.approx(26.76, abs=0.05)
    assert tl.loc["2050 +2,2 °C sans froid", "Maximum °C"] == pytest.approx(33.77, abs=0.1)


def test_sensibilite_chambres(modele, d):
    sc = sizing.sensibilite_chambres(modele, d, 2.2)
    assert sc.loc[(120.0, "nuit seule"), "Pic froid (MW)"] == pytest.approx(2.65, abs=0.03)
    assert sc.loc[(120.0, "24h/24"), "Pic froid (MW)"] == pytest.approx(0.66, abs=0.03)


# ------------------------------------------------------------------ Partie 3
def test_pic_2050(modele, d):
    r = sizing.puissance_froid(modele, d, 2.2, mode="reactif")
    assert r.pic_MW == pytest.approx(2.65, abs=0.03)   # critère dimensionnant V3
    assert r.energie_MWh == pytest.approx(73.8, abs=0.5)


def test_contribution_chambres(modele, d):
    r = sizing.puissance_froid(modele, d, 2.2, mode="reactif")
    part = r.energie_zone["Chambres"] / r.energie_MWh
    assert part == pytest.approx(0.421, abs=0.01)     # doc 42,1 %


def test_marges_2050(modele, d):
    _, res = sizing.tableau_dimensionnement(modele, d)
    marges = sizing.tableau_marges(res)
    ligne = marges.loc["2050 +2,2 °C"]
    assert ligne["Marge 2 MW"] == pytest.approx(-0.65, abs=0.03)
    assert ligne["Marge 2.5 MW"] == pytest.approx(-0.15, abs=0.03)
    assert ligne["Marge 3 MW"] == pytest.approx(0.35, abs=0.03)


def test_saturation_2050(modele, d):
    _, res = sizing.tableau_dimensionnement(modele, d)
    sat = sizing.tableau_saturation(res)
    assert sat.loc["2050 +2,2 °C", "Saturation 3 MW"] == 0


def test_pilotage_anticipatif_ecrete(modele, d):
    reac = sizing.puissance_froid(modele, d, 2.2, mode="reactif")
    anti = sizing.puissance_froid(modele, d, 2.2, mode="anticipatif")
    assert anti.pic_MW < reac.pic_MW          # anticipatif écrête les pointes
    assert anti.energie_MWh == pytest.approx(reac.energie_MWh, rel=0.05)
