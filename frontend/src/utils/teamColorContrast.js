// Règles de contraste du monogramme d'équipe (docs/design-v1.md §5.7, §10.3).
//
// Deux seuils, pour deux rôles différents sur le même badge :
// - le FOND du badge doit rester visible comme forme colorée sur la carte
//   (bg-surface) -- indicateur graphique, WCAG 1.4.11, seuil 3:1 (déjà
//   retenu pour le filet, inchangé en passant au badge).
// - le TRICODE écrit DANS le badge est du texte normal -- §12/WCAG 1.4.3,
//   seuil 4,5:1, contre le fond du badge lui-même (pas contre la carte).
import {
  contrastRatio,
  hexToOklab,
  isInSrgbGamut,
  oklabToHex,
  oklabToOklch,
  oklchToOklab,
  relativeLuminance,
} from './colorSpace'

export const MIN_BADGE_FILL_CONTRAST = 3
export const MIN_BADGE_TEXT_CONTRAST = 4.5

// Les deux seules couleurs de texte candidates pour "s'asseoir" sur un fond
// de badge -- littéralement les tokens --text des deux modes (quasi blanc
// sombre, quasi noir clair), jamais un blanc/noir pur inventé pour
// l'occasion : ce sont déjà les deux extrêmes que l'app utilise et a
// mesurés ailleurs (style.css §5.2/§5.3).
const NEAR_WHITE_TEXT = '#F5F5F7'
const NEAR_BLACK_TEXT = '#14161C'

function maxChromaInGamut(L, chromaCeiling, hue) {
  let lo = 0
  let hi = chromaCeiling
  for (let i = 0; i < 30; i += 1) {
    const mid = (lo + hi) / 2
    if (isInSrgbGamut(oklchToOklab({ L, C: mid, H: hue }))) {
      lo = mid
    } else {
      hi = mid
    }
  }
  return lo
}

// Ajuste la CLARTÉ (L) à teinte (H) et chroma (C) constants, jusqu'à
// atteindre `minContrast` contre `backgroundHex` -- méthode OKLCH
// (2026-09-02, remplace l'ancien réglage en HSL). Ne réduit le chroma que
// si le point (L, C, H) sort du gamut sRGB à ce niveau de clarté : jamais
// une désaturation systématique, seulement le filet de sécurité nécessaire
// pour rester représentable. Direction déterminée par la luminosité du
// FOND (on s'en éloigne), jamais une correction saisie à la main par
// équipe -- une seule règle pour les 6 (bientôt 30) couleurs et les deux
// modes.
//
// Pourquoi OKLCH et pas HSL (défaut initial, abandonné) : à teinte et
// saturation HSL constantes, éclaircir une couleur très sombre peut faire
// dériver sa TEINTE PERÇUE -- mesuré sur Denver, #0E2240 (marine) devenait
// #2B69C6 (bleu franc, plus la même couleur) une fois éclairci à 3:1 en
// HSL. OKLCH est construit pour rester perceptuellement uniforme : à H
// constant, seule la clarté change, la couleur reste reconnaissable comme
// une variante plus claire de la même teinte.
export function adjustForContrast(hex, backgroundHex, minContrast = MIN_BADGE_FILL_CONTRAST) {
  if (contrastRatio(hex, backgroundHex) >= minContrast) return hex

  const { L: L0, a: a0, b: b0 } = hexToOklab(hex)
  const { C: C0, H } = oklabToOklch({ L: L0, a: a0, b: b0 })
  const backgroundIsDark = relativeLuminance(backgroundHex) < 0.5
  const step = backgroundIsDark ? 0.01 : -0.01

  let L = L0
  let candidate = hex
  for (let i = 0; i < 200; i += 1) {
    L += step
    L = Math.max(0, Math.min(1, L))
    let C = C0
    if (!isInSrgbGamut(oklchToOklab({ L, C, H }))) {
      C = maxChromaInGamut(L, C0, H)
    }
    candidate = oklabToHex(oklchToOklab({ L, C, H }))
    if (contrastRatio(candidate, backgroundHex) >= minContrast) return candidate
    if (L <= 0 || L >= 1) break
  }
  return candidate
}

// Couleur du tricode À L'INTÉRIEUR du badge : le blanc ou le noir "de
// l'app" (jamais une 3e teinte, jamais une couleur qui coderait autre
// chose), celui des deux qui contraste le plus contre le fond du badge.
// Mathématiquement, pour tout fond, l'un des deux extrêmes atteint 4,5:1
// (les deux formules de contraste WCAG contre blanc et contre noir se
// croisent avant leurs seuils respectifs -- vérifié : aucun fond ne peut
// faire échouer les deux à la fois) ; le ratio est quand même retourné et
// vérifié par test, jamais supposé.
export function pickBadgeTextColor(fillHex) {
  const contrastWithWhite = contrastRatio(fillHex, NEAR_WHITE_TEXT)
  const contrastWithBlack = contrastRatio(fillHex, NEAR_BLACK_TEXT)
  return contrastWithWhite >= contrastWithBlack
    ? { color: NEAR_WHITE_TEXT, ratio: contrastWithWhite }
    : { color: NEAR_BLACK_TEXT, ratio: contrastWithBlack }
}
