# Calibrage V1 du moteur de pronostics

> **Calibrage V1 basé sur des données simulées, à revalider avec de vraies données de saison (Étape 7, ou au fil de la saison 2025-26).** Les valeurs ci-dessous sont un point de départ raisonné, pas une vérité définitive — elles seront recalibrées dès que de vrais résultats de matchs seront disponibles.

## Le problème

Formule de la Note Finale :

```
Note Finale = (Note de Base × Curseur A) − (PER des absents × Curseur B) − Malus Calendrier + Bonus Draft
```

`win_pct` (Note de Base) vit sur une échelle **0–1**. Le PER vit sur une échelle **~10–30** (le PER est construit pour que la moyenne de la ligue soit toujours 15, quelle que soit la saison). Avec les multiplicateurs neutres (1.0/1.0) utilisés par défaut jusqu'à l'Étape 5, soustraire un PER brut à un `win_pct` brut faisait que la blessure d'un titulaire quelconque écrasait totalement la note de base — un problème repéré dès l'Étape 3 mais non résolu faute de données concrètes pour le calibrer.

## La solution : une échelle commune de points (0–100)

- **`base_note_multiplier` : 1.0 → 100.0.** `win_pct` (0–1) devient une note de base 0–100 (typiquement 20 à 85 pour des équipes réelles) — une échelle intuitive, proche des "ratings" utilisés dans l'analytique NBA réelle.
- **`per_impact_multiplier` : 1.0 → 0.4.** Un titulaire absent représente alors un impact réel mais pas écrasant :

  | PER absent | Malus (points) |
  |---|---|
  | 15 (rotation moyenne) | 6 |
  | 20 (bon titulaire) | 8 |
  | 25 (all-star) | 10 |
  | 30 (MVP) | 12 |

- **`back_to_back_penalty` : 0.0 → 2.0**, **`three_in_four_penalty` : 0.0 → 3.5** — ces deux malus étaient inertes par défaut jusqu'ici (aucun effet tant que l'admin ne configurait rien). Le 3-en-4 reste volontairement plus sévère que le B2B, pour que la règle "le plus sévère l'emporte" (validée à l'Étape 3, pas de cumul des deux) le favorise naturellement quand les deux s'appliquent au même match.
- **`mpg_threshold` (15.0)** : inchangé, ce n'est pas un problème d'échelle.
- **`draft_bonus_config`** : reste configurable par l'admin (vide par défaut), mais un exemple calibré sur la même échelle est utilisé dans les tests/simulations : `{"1": 8.0, "2": 6.0, "3": 4.0}` (décroissant avec le rang de pick).

## Les seuils de fiabilité : calibrés sur des données, pas dans l'abstrait

Plutôt que de fixer `reliability_threshold_low`/`high` par intuition seule, un calendrier de 6 équipes fictives a été simulé (`tests/simulation_data.py` — 6 équipes de force variée, effectifs réalistes, blessures, B2B/3in4, une équipe en début de saison) et `compute_matchup` a été exécuté sur l'ensemble des matchs de ce calendrier plus une série de scénarios ciblés (star blessée, cumul d'absences, fatigue isolée...).

**Distribution réelle des `|spread|` obtenue (13 matchs/scénarios) :**

```
min     = 0.0
median  = 18.5
mean    = 24.3
max     = 58.0
triée   = [0.0, 2.0, 2.0, 3.5, 10.3, 14.6, 18.5, 25.0, 40.5, 43.0, 43.4, 55.0, 58.0]
```

Deux ruptures nettes apparaissent dans cette distribution :
- entre **3.5 et 10.3** (écarts issus d'effets isolés/faibles : fatigue seule, quasi-renversement d'un match serré) et les écarts "réels" de matchs joués ;
- entre **25.0 et 40.5** (matchs serrés/moyens) et les gros mismatches structurels.

**Seuils retenus, au milieu de ces deux ruptures :**

- `reliability_threshold_low` : **7.0** *(milieu de l'écart 3.5 → 10.3)*
- `reliability_threshold_high` : **30.0** *(dans l'écart 25.0 → 40.5)*

Avec ces seuils, la distribution simulée se répartit ainsi :
- **Faible** (< 7.0) : 4 matchs — fatigue isolée, quasi-renversements.
- **Moyenne** (7.0–30.0) : 4 matchs — écarts réels mais incertains.
- **Forte** (≥ 30.0) : 5 matchs — mismatches structurels nets.

## Scénarios de validation (cohérence avec l'intuition basket)

Vérifiés dans `tests/test_calibration_scenarios.py` :

1. **Favori serré perd son meilleur joueur** → bascule vers l'outsider, mais fiabilité **Faible** (écart < 10 points) : pas un renversement "absurde", juste un match qui devient un vrai coin-flip.
2. **Joueur de banc sous le seuil MPG blessé** → aucun effet sur la note (filtre `mpg_threshold` intact).
3. **Star blessée dans un gros mismatch** (BOS fort perd son meilleur joueur PER 29 contre DET faible) → BOS **reste favori**, fiabilité toujours **Forte**. *Le scénario qui répond directement à l'inquiétude de l'Étape 3 : le malus PER ne doit pas écraser un écart de niveau important — confirmé.*
4. **B2B isolé** (équipes à force égale) → désavantage de 2 points, fiabilité Faible.
5. **3in4 isolé** → désavantage de 3.5 points (plus sévère que le B2B seul), fiabilité Faible.
6. **3in4 + B2B simultanés** (vérifié bout en bout, pas juste sur la fonction de calcul isolée) → seul le malus 3in4 (3.5) s'applique, pas la somme (5.5).
7. **Règle des 10 premiers matchs** → une équipe à 3 matchs joués utilise son `win_pct` N-1, pas celui de la saison en cours.
8. **Bonus draft** → actif uniquement tant que l'équipe est en "début de saison".
9. **Cumul de 2 titulaires absents** → impact significatif (peut suffire à renverser un match moyennement favorable, ex: +14.6 sur le calendrier simulé), mais toujours une valeur finie et raisonnable.
10. **Garde-fou sur tout le calendrier simulé** → aucun `|spread|` n'explose (< 100 dans tous les cas testés), les trois niveaux de fiabilité apparaissent bien sur un calendrier varié.

## Limites connues de ce calibrage V1

- Basé sur **6 équipes fictives et un calendrier synthétique**, pas sur de vraies statistiques de saison. Les win_pct, PER et enchaînements de calendrier simulés sont plausibles mais arbitraires.
- Les seuils de fiabilité reflètent la distribution de **ce** calendrier simulé précis — une vraie saison NBA (82 matchs × 30 équipes, une bien plus grande variété de matchups) produira probablement une distribution différente, à réobserver avec de vraies données.
- Le terme "Bonus/Malus Transferts" du cahier des charges reste hors périmètre (voir `CLAUDE.md`) et n'est donc pas calibré ici.

**À refaire dès que possible avec de vraies données** : relancer le même exercice (générer la distribution des `|spread|` sur une vraie tranche de saison une fois les stats et blessures réelles importées) et ajuster `reliability_threshold_low/high` — et si besoin `per_impact_multiplier` — en conséquence.
