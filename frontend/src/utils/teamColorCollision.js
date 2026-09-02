import { oklabDistance } from './colorSpace'

// Distance perceptuelle entre deux couleurs d'équipe (docs/design-v1.md
// §5.7) : euclidienne dans l'espace CARTÉSIEN OKLab (ΔL, Δa, Δb), jamais
// CIEDE2000 (bien plus complexe pour un gain marginal ici, alors qu'OKLab a
// justement été conçu pour qu'une distance euclidienne simple corrèle bien
// avec CIEDE2000) et jamais sur les coordonnées cylindriques OKLCH
// directement (mélanger un angle de teinte en degrés avec des unités de
// clarté/chroma dans une même formule euclidienne n'a pas de sens -- on
// reconvertit toujours en (L, a, b) cartésien avant de mesurer).
export const oklabColorDistance = oklabDistance

// Seuil retenu : 0,15. Calibré empiriquement sur 10 paires de teintes
// officielles (couleurs de notoriété publique, même réserve de précision
// qu'ailleurs en §5.7) : les paires reconnues comme un vrai risque de
// confusion (rouges Miami/Chicago/Toronto, marines Détroit/Denver/Indiana/
// Utah, violet/marine très sombres Charlotte/Denver) restent toutes sous
// 0,12 ; les paires manifestement distinctes (n'importe laquelle contre le
// vert de Boston, par exemple) sautent à 0,27 et au-delà -- un écart net
// d'un facteur ~2,3 entre les deux groupes. 0,15 passe au milieu de cet
// écart, avec une marge confortable des deux côtés : une petite imprécision
// sur une teinte de notoriété publique ne fait basculer aucun cas connu
// d'un côté à l'autre du seuil.
//
// RÉSERVE EXPLICITE : calibré sur 10 paires, pas sur les 435 combinaisons
// des 30 équipes de la ligue. À revalider une fois la table complète
// assemblée -- une paire non encore rencontrée pourrait se nicher dans
// l'écart et remettre en cause le seuil.
export const COLLISION_THRESHOLD_OKLAB = 0.15

// Calculée sur les couleurs OFFICIELLES BRUTES (constants/teamColors.js),
// JAMAIS sur le rendu ajusté par teamColorContrast.js -- décision explicite
// (2026-09-02) : une collision est une propriété des deux identités de
// marque, indépendante du mode. La calculer sur le rendu ferait dépendre la
// bascule primaire/secondaire du mode clair/sombre -- une équipe changerait
// de couleur au bascule du thème, ce que le troisième axe (§5.7) interdit
// déjà par principe pour la teinte elle-même.
export function haveColorCollision(hexA, hexB, threshold = COLLISION_THRESHOLD_OKLAB) {
  return oklabColorDistance(hexA, hexB) < threshold
}
