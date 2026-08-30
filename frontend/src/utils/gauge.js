// Calcul du déport de la jauge divergente (docs/design-v1.md §10.1), isolé du
// rendu pour rester testable sans DOM (voir gauge.test.js). Le déport suit le
// même signe que `spread` (home_team_note - away_team_note, positif = domicile
// favori, voir app/models/prediction.py) : positif -> déport côté domicile,
// négatif -> déport côté extérieur.
//
// Le déport maximal (+-1) est atteint à `thresholdHigh` (reliability_threshold_high,
// jamais une constante en dur -- voir docs/design-v1.md §10.1 "Conséquence importante").
// Au-delà, écrêté à +-1 : un écart de 58 ne mérite pas plus d'appui visuel qu'un
// écart de 30, les deux relevant déjà de la même décision.
export function computeGaugeOffset(spread, thresholdHigh) {
  if (!thresholdHigh) return 0
  const ratio = spread / thresholdHigh
  return Math.max(-1, Math.min(1, ratio))
}
