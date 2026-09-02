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

// Seuil retenu : 0,03 -- recalibré le 2026-09-02 après un changement
// d'OBJECTIF, pas un simple réglage plus fin du même objectif (voir
// docs/design-v1.md §5.7, "Recadrage"). Un seuil à 0,15 (abandonné) répond
// à "ces deux teintes sont-elles de la même famille ?" -- la question
// pertinente pour une identification ABSOLUE par la seule couleur, un
// objectif explicitement écarté : le tricode identifie déjà l'équipe, la
// couleur n'a plus qu'à garantir que les deux badges D'UNE MÊME CARTE se
// perçoivent comme deux objets distincts (discrimination LOCALE, pas un
// placement global des 30 teintes de la ligue).
//
// Calibré sur des vignettes RENDUES à la taille réelle du badge (40×40px,
// mode sombre), pas en théorie : jusqu'à ΔE_OK≈0,025 (ex. deux rouges à
// 0,0247), les deux badges se perçoivent comme UN SEUL bloc de couleur. À
// partir de ΔE_OK≈0,035-0,045, une différence redevient perceptible -- deux
// teintes cousines, mais deux. 0,03 tombe dans l'écart entre ces deux
// groupes (0,0247 → 0,0354, un facteur ~1,4), dans une zone plate où le
// nombre de paires touchées ne bouge pas (20 sur 435 à 0,025 comme à 0,035).
//
// Mesuré sur les 435 paires des 30 équipes (couleurs de notoriété publique,
// San Antonio en argent -- voir §5.7) : 20 paires, soit 4,6 %, sous la barre
// de 15 % attendue. Neuf de ces vingt sont des couleurs officielles
// STRICTEMENT IDENTIQUES dans cet échantillon (ex. Chicago/Houston/Toronto,
// même rouge) -- aucun seuil ne les aurait jamais séparées, un fait des
// données, pas un artefact de calibrage.
//
// RÉSERVE EXPLICITE, inchangée dans son principe : calibré sur un
// échantillon de paires vérifiées par rendu, pas sur les 435 combinaisons
// revues une à une à l'œil. Les 20 paires retenues ont été inspectées
// individuellement ; les 415 autres sont supposées distinctes sur la seule
// base du seuil.
export const COLLISION_THRESHOLD_OKLAB = 0.03

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
