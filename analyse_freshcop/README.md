# Analyse FRESHCOP — Modèle thermique dynamique (Chapitre 4 consolidé V3)

Code Python reproduisant **l'ensemble des analyses et calculs** définis dans
`FRESHCOP_Chapitre4_Consolide_Corrections_V3_Recentrage_1_2_3.docx`, calibrés
sur le fichier de mesures `T appart mai - jin 26.csv`.

Le modèle transforme les mesures horaires de température de la résidence
(Paris XV, ~440 logements) en un dimensionnement dynamique du réseau collectif
de froid FRESHCOP, et conclut sur l'arbitrage **2 MW / 2,5 MW / 3 MW**.

---

## Installation

```bash
cd analyse_freshcop
pip install -r requirements.txt
```

## Utilisation

```bash
# Analyse complète : tableaux à l'écran + export CSV + figures PNG
python run_analysis.py

# Options
python run_analysis.py --csv "../T appart mai - jin 26.csv" \
                       --sorties sorties \
                       --coeffs one_step \   # ou free_run (calibration Partie 1)
                       --sans-figures
```

Les résultats sont écrits dans `sorties/tableaux/` (CSV) et `sorties/figures/`
(PNG). Chaque tableau affiché est comparé aux valeurs documentées.

Tests de non-régression :

```bash
pytest -q
```

---

## Ce que fait le code (dans l'ordre du document)

| Section doc | Module | Calcul reproduit |
|---|---|---|
| §4.2 | `data.py` | Lecture CSV, cadrage 22/05→30/06 (960 h), moyenne AB/CD |
| §4.3 | `stats.py` | Statistiques descriptives, heures de dépassement, degrés-heures |
| §4.6–4.7 | `calibration.py` | Identification du modèle RC (one-step **et** free-run) |
| §4.8 | `stats.py` | Déphasage (corrélation croisée), refroidissement nocturne |
| §4.9 | `calibration.py` | Conversion coefficients apparents → C, UA, Psol, Pres |
| §4.2.2 | `simulation.py` | Températures libres 2026 / 2050 / 2100 |
| §4.2.3 | `simulation.py` | Dépassement des cibles par zone |
| §4.2.8 | `simulation.py` | Métrique V3 « nuits chaudes » |
| §4.2.9 / §4.3.11 | `sizing.py` | Sensibilités (capacité thermique, prudence, pilotage) |
| §4.2.5 / §4.3.14 | `sizing.py` | Puissance froid horaire (trajectoire contrôlée) |
| §4.3.6–4.3.8 | `sizing.py` | Dimensionnement, marges, saturation par scénario |
| §4.3.9–4.3.10 | `sizing.py` | Contribution des zones et du vitrage |
| §4.3.12 | `sizing.py` | Effet du pilotage réactif vs anticipatif |
| §4.4 | `sizing.py` | Tableau de décision consolidé V3 |

## Le modèle en bref

Modèle **RC équivalent** à pas horaire (le 2R2C conceptuel n'est pas
identifiable avec une seule sortie moyenne, §4.5) :

```
T_int(t+1) = T_int(t) + a·[T_ext(t) − T_int(t)] + b·Rad(t) + c
```

**Deux calibrations**, toutes deux reproduites depuis le CSV :

| Méthode | a | τ = 1/a | RMSE | R² | Usage |
|---|---|---|---|---|---|
| `free_run` (trajectoire) | 0,00304 | 330 h | 1,32 °C | 0,81 | Référence Partie 1 |
| `one_step` (moindres carrés) | 0,00363 | 275 h | 1,73 °C | 0,67 | Simulations Parties 2/3 |

**Puissance froid** (§4.2.5) : simulation par sous-groupe *zone × vitrage* sur
une trajectoire *contrôlée*. À chaque heure, si la température prévue dépasse la
consigne, on applique la puissance qui ramène le sous-groupe à sa consigne :

```
Q_i(t) = max(0 ; T_libre,i(t+1) − T_cible,i(t+1)) · C_i / Δt
C_i    = C_total · part_surface_zone · part_parc_vitrage
```

Le **pic réactif** est piloté par la transition de consigne des chambres à 20 h
(26 °C → 24 °C), ce qui rend les chambres **dimensionnantes**.

## Fidélité au document

Les grandeurs qui **pilotent la décision** sont reproduites au dixième près :

| Grandeur (scénario 2050) | Document | Calculé |
|---|---|---|
| Pic non contraint | 2,65 MW | **2,65 MW** |
| Énergie froide période | 73,8 MWh | **73,8 MWh** |
| Marges 2 / 2,5 / 3 MW | −0,65 / −0,15 / +0,35 | **−0,65 / −0,15 / +0,35** |
| Saturation 2 / 2,5 / 3 MW | 3 / 1 / 0 h | **3 / 1 / 0 h** |
| Part chambres | 42,1 % | **42,1 %** |
| Constante de temps (P1) | 330 h | **329 h** |
| Déphasage brut / journalier | 51 h / 3 h | **51 h / 3 h** |
| Refroidissement nocturne | 8,4 / 0,6 °C | **8,4 / 0,6 °C** |

### Écarts connus / choix de modélisation

- **Répartition énergie par vitrage (§4.3.10)** : le code obtient ≈72 %/28 %
  (simple/double) contre 81,3 %/18,7 % au document. Le facteur de vitrage est
  ici appliqué au *gain horaire* (ce qui reproduit exactement le pic et
  l'énergie totale). La répartition documentée semble calculée sur une base
  différente (température libre non contrôlée) ; c'est une incohérence interne
  au document sur cette **métrique secondaire** — le pic et l'énergie, eux, sont
  exacts.
- **Heures actives / P95 (§4.3.6)** : le document ne définit pas précisément le
  seuil d'« heure active » ; les valeurs (pic, énergie, marges) restent exactes.
- La **capacité thermique absolue** est une hypothèse d'échelle (120 Wh/m².K) ;
  seule la dynamique UA/C est identifiée (§4.9). La plage 80–165 Wh/m².K est
  balayée en sensibilité.

## Structure

```
analyse_freshcop/
├── freshcop/
│   ├── config.py        # hypothèses & constantes (mesuré / identifié / supposé)
│   ├── data.py          # lecture & cadrage CSV
│   ├── stats.py         # statistiques, degrés-heures, déphasage, nuit
│   ├── calibration.py   # identification RC + conversion physique
│   ├── simulation.py    # températures libres, zones, nuits chaudes
│   ├── sizing.py        # puissance froid, marges, saturation, sensibilités
│   └── figures.py       # figures matplotlib
├── tests/test_validation.py   # 15 tests de non-régression vs document
├── run_analysis.py      # exécution complète
├── requirements.txt
└── sorties/             # tableaux CSV + figures PNG (générés)
```

> **Statut** : document de travail — pré-dimensionnement. Non substituable à une
> étude thermique détaillée logement par logement (cf. §4.10 du document).
