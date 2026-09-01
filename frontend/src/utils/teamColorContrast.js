// Règle de contraste du filet de couleur d'équipe (docs/design-v1.md §5.7).
//
// Seuil retenu : 3:1, WCAG 1.4.11 "Non-text Contrast" -- le filet est un
// indicateur GRAPHIQUE (aucun texte dessus), pas un texte : le seuil de
// 4,5:1 (§12, texte normal) ne s'applique pas ici. Même seuil déjà retenu
// dans ce projet pour un indicateur non textuel équivalent (le contour de
// focus clavier, voir style.css) -- cohérence délibérée, pas une
// coïncidence.
export const MIN_RAIL_CONTRAST = 3

function hexToRgb(hex) {
  const clean = hex.replace('#', '')
  return {
    r: parseInt(clean.slice(0, 2), 16),
    g: parseInt(clean.slice(2, 4), 16),
    b: parseInt(clean.slice(4, 6), 16),
  }
}

function rgbToHex({ r, g, b }) {
  const toHex = (c) =>
    Math.round(Math.min(255, Math.max(0, c)))
      .toString(16)
      .padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

// Luminance relative WCAG -- même formule que celle appliquée manuellement
// pendant le diagnostic pixel par pixel de la jauge divergente
// (docs/design-v1.md §10.1), désormais encodée une fois pour toutes ici.
function relativeLuminance({ r, g, b }) {
  const lin = (c) => {
    const s = c / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export function contrastRatio(hexA, hexB) {
  const lA = relativeLuminance(hexToRgb(hexA))
  const lB = relativeLuminance(hexToRgb(hexB))
  const lighter = Math.max(lA, lB)
  const darker = Math.min(lA, lB)
  return (lighter + 0.05) / (darker + 0.05)
}

function rgbToHsl({ r, g, b }) {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0)
  else if (max === gn) h = (bn - rn) / d + 2
  else h = (rn - gn) / d + 4
  return { h: h / 6, s, l }
}

function hue2rgb(p, q, t) {
  let tt = t
  if (tt < 0) tt += 1
  if (tt > 1) tt -= 1
  if (tt < 1 / 6) return p + (q - p) * 6 * tt
  if (tt < 1 / 2) return q
  if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6
  return p
}

function hslToRgb({ h, s, l }) {
  if (s === 0) {
    const v = l * 255
    return { r: v, g: v, b: v }
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return {
    r: hue2rgb(p, q, h + 1 / 3) * 255,
    g: hue2rgb(p, q, h) * 255,
    b: hue2rgb(p, q, h - 1 / 3) * 255,
  }
}

// Ajuste UNIQUEMENT la luminosité (teinte H et saturation S inchangées --
// la couleur reste reconnaissable comme celle de l'équipe) jusqu'à
// atteindre `minContrast` contre `backgroundHex`. Direction déterminée par
// la luminosité du FOND (on s'en éloigne) : jamais une correction saisie à
// la main équipe par équipe, une seule règle pour les deux modes et les 6
// (bientôt 30) couleurs.
//
// Bornes 0.02/0.98 plutôt qu'une boucle sans fin : une teinte totalement
// désaturée n'atteindrait jamais un grand contraste par ce seul biais.
// Jamais atteint pour les 6 couleurs actuelles (voir docs/design-v1.md
// §5.7, tableau de contraste mesuré) -- filet de sécurité, pas un cas
// rencontré en pratique.
export function adjustForContrast(hex, backgroundHex, minContrast = MIN_RAIL_CONTRAST) {
  if (contrastRatio(hex, backgroundHex) >= minContrast) return hex

  const backgroundIsDark = relativeLuminance(hexToRgb(backgroundHex)) < 0.5
  const hsl = rgbToHsl(hexToRgb(hex))
  const step = backgroundIsDark ? 0.02 : -0.02
  let l = hsl.l

  while (l > 0.02 && l < 0.98) {
    l += step
    const candidate = rgbToHex(hslToRgb({ ...hsl, l }))
    if (contrastRatio(candidate, backgroundHex) >= minContrast) return candidate
  }
  return rgbToHex(hslToRgb({ ...hsl, l: backgroundIsDark ? 0.98 : 0.02 }))
}
