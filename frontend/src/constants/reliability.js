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
// Le niveau de fiabilité n'a plus de couleur de BARRE PROPRE (voir
// DivergentGauge.vue) -- élevée et modérée restent toutes deux bg-accent,
// jamais distinguées par la barre elle-même. Retour en arrière assumé
// (2026-08-31, recette manuelle) : la barre colorée par niveau doublait
// l'information déjà annoncée par cette même pastille, sans jamais dire QUI
// est favori (la couleur ne distinguait pas les deux côtés -- seule la
// position le fait). Voir docs/design-v1.md §10.1.
//
// "Faible" reste un cas à part, PAS un 3e code couleur de la barre : §10.2
// retire tout accent de la carte entière pour ce niveau (refus de
// recommander), jauge et note du favori comprises -- GameCard.vue passe
// `muted` à DivergentGauge.vue quand `reliability === 'faible'`, une
// absence d'accent, jamais une couleur qui identifierait ce niveau.
export const RELIABILITY_TREATMENT = {
  // pillClass : traitement de la pastille de mention (§10.3 Ligne 1) --
  //   "accent coloré PLEIN" pour forte (le seul niveau qui mérite un aplat
  //   plein, --accent-on comme texte, voir docs/design-v1.md §5.2/§5.3),
  //   "ambre ATTÉNUÉ"/"gris ATTÉNUÉ" pour les deux autres (translucide).
  forte: {
    pillClass: 'bg-accent text-accent-on',
    mention: 'Confiance élevée',
  },
  moyenne: {
    pillClass: 'bg-warning/15 text-warning',
    mention: 'Confiance modérée',
  },
  faible: {
    pillClass: 'bg-neutral/15 text-neutral',
    mention: 'Trop serré',
  },
}

export function reliabilityTreatment(reliability) {
  return RELIABILITY_TREATMENT[reliability] ?? RELIABILITY_TREATMENT.faible
}
