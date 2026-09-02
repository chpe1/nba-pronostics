// Conversions colorimétriques partagées (docs/design-v1.md §5.7) : sRGB <->
// OKLab/OKLCH (Björn Ottosson) + luminance/contraste WCAG. Un seul endroit
// pour cette math, réutilisé par l'ajustement de contraste des badges
// d'équipe (teamColorContrast.js) ET par la distance perceptuelle de
// collision (teamColorCollision.js) -- jamais deux implémentations de la
// même conversion à maintenir en cohérence séparément (voir §13 du même
// document pour un précédent où deux implémentations divergentes d'une
// même notion avaient fini par se désynchroniser).

export function hexToRgb(hex) {
  const clean = hex.replace('#', '')
  return {
    r: parseInt(clean.slice(0, 2), 16),
    g: parseInt(clean.slice(2, 4), 16),
    b: parseInt(clean.slice(4, 6), 16),
  }
}

export function rgbToHex({ r, g, b }) {
  const toHex = (c) =>
    Math.round(Math.min(255, Math.max(0, c)))
      .toString(16)
      .padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase()
}

function srgbToLinearChannel(c) {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

function linearToSrgbChannel(c) {
  const clamped = Math.max(0, Math.min(1, c))
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055
}

// Luminance relative WCAG -- inchangée depuis le diagnostic pixel par pixel
// de la jauge divergente (docs/design-v1.md §10.1).
export function relativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex)
  return 0.2126 * srgbToLinearChannel(r) + 0.7152 * srgbToLinearChannel(g) + 0.0722 * srgbToLinearChannel(b)
}

export function contrastRatio(hexA, hexB) {
  const lA = relativeLuminance(hexA)
  const lB = relativeLuminance(hexB)
  const lighter = Math.max(lA, lB)
  const darker = Math.min(lA, lB)
  return (lighter + 0.05) / (darker + 0.05)
}

// ---- sRGB (linéaire) <-> OKLab -----------------------------------------
// Matrices telles que publiées par Björn Ottosson (https://bottosson.github.io/posts/oklab/).
function cbrtSigned(x) {
  return Math.sign(x) * Math.abs(x) ** (1 / 3)
}

function linearRgbToOklab(r, g, b) {
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

  const l_ = cbrtSigned(l)
  const m_ = cbrtSigned(m)
  const s_ = cbrtSigned(s)

  return {
    L: 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_,
    a: 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_,
    b: 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_,
  }
}

function oklabToLinearRgb({ L, a, b }) {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b

  const l = l_ ** 3
  const m = m_ ** 3
  const s = s_ ** 3

  return {
    r: 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    g: -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    b: -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  }
}

export function hexToOklab(hex) {
  const { r, g, b } = hexToRgb(hex)
  return linearRgbToOklab(srgbToLinearChannel(r), srgbToLinearChannel(g), srgbToLinearChannel(b))
}

export function oklabToHex({ L, a, b }) {
  const { r, g, b: b2 } = oklabToLinearRgb({ L, a, b })
  return rgbToHex({
    r: linearToSrgbChannel(r) * 255,
    g: linearToSrgbChannel(g) * 255,
    b: linearToSrgbChannel(b2) * 255,
  })
}

// Un candidat OKLab est "hors gamut" si sa conversion en RGB linéaire sort
// de [0,1] sur un canal -- signe que la couleur n'est pas représentable en
// sRGB avant même la quantification 8 bits.
export function isInSrgbGamut({ L, a, b }) {
  const { r, g, b: b2 } = oklabToLinearRgb({ L, a, b })
  const eps = 1e-4
  return [r, g, b2].every((v) => v >= -eps && v <= 1 + eps)
}

export function oklabToOklch({ L, a, b }) {
  const C = Math.hypot(a, b)
  const H = (Math.atan2(b, a) * 180) / Math.PI
  return { L, C, H: H < 0 ? H + 360 : H }
}

export function oklchToOklab({ L, C, H }) {
  const rad = (H * Math.PI) / 180
  return { L, a: C * Math.cos(rad), b: C * Math.sin(rad) }
}

export function oklabDistance(hexA, hexB) {
  const a = hexToOklab(hexA)
  const b = hexToOklab(hexB)
  return Math.hypot(a.L - b.L, a.a - b.a, a.b - b.b)
}
