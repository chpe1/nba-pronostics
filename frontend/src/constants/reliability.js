// Mapping niveau de fiabilité -> traitement visuel (docs/design-v1.md §10.2,
// recette-design-lot2.md Point 4). Clés = valeurs exactes de l'enum backend
// (ReliabilityLevel, app/models/prediction.py) : "faible"/"moyenne"/"forte".
//
// Point signalé (à trancher par l'utilisateur, pas résolu ici) : §5.4 du même
// document liste "confiance élevée" dans la ligne sémantique "succès" (vert),
// alors que ce tableau §10.2 assigne "Forte" à l'ACCENT (orange). Les deux
// sections se contredisent. Implémenté ici selon §10.2/la table explicite de
// recette-design-lot2.md (source la plus récente et la plus opérationnelle
// pour ce lot) -- accent pour "forte", pas success.
export const RELIABILITY_TREATMENT = {
  // barFill : toujours un aplat plein, utilisé par la barre de DivergentGauge.vue
  //   (un fond translucide n'y lirait pas assez sur une jauge fine).
  // pillClass : traitement de la pastille de mention (§10.3 Ligne 1) --
  //   "accent coloré PLEIN" pour forte (le seul niveau qui mérite un aplat
  //   plein, --accent-on comme texte, voir docs/design-v1.md §5.2/§5.3),
  //   "ambre ATTÉNUÉ"/"gris ATTÉNUÉ" pour les deux autres (translucide).
  forte: {
    barFill: 'bg-accent',
    pillClass: 'bg-accent text-accent-on',
    mention: 'Confiance élevée',
  },
  moyenne: {
    barFill: 'bg-warning',
    pillClass: 'bg-warning/15 text-warning',
    mention: 'Confiance modérée',
  },
  faible: {
    barFill: 'bg-neutral',
    pillClass: 'bg-neutral/15 text-neutral',
    mention: 'Trop serré',
  },
}

export function reliabilityTreatment(reliability) {
  return RELIABILITY_TREATMENT[reliability] ?? RELIABILITY_TREATMENT.faible
}
