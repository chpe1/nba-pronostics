import { TEAM_COLORS } from '@/constants/teamColors'
import { adjustForContrast, pickBadgeTextColor } from './teamColorContrast'
import { haveColorCollision } from './teamColorCollision'

// Miroir de --surface (style.css, §5.2/§5.3) par mode -- fond réel sur
// lequel le badge d'équipe se pose dans GameCard.vue (bg-surface, jamais
// bg-canvas). Dupliqué à dessein plutôt que lu via getComputedStyle : même
// pattern déjà en place dans ce projet pour le meta theme-color
// (stores/theme.js, dupliqué avec index.html) -- à TENIR À JOUR si
// --surface change de valeur dans style.css.
const SURFACE_BY_THEME = {
  dark: '#1a1d26',
  light: '#ffffff',
}

function badgeFromRawColor(rawHex, backgroundHex) {
  const fill = adjustForContrast(rawHex, backgroundHex)
  const { color: text } = pickBadgeTextColor(fill)
  return { fill, text }
}

// Couleurs du monogramme des deux équipes d'un match (docs/design-v1.md
// §5.7/§10.3) : {fill, text} par équipe, ou null si l'équipe est hors du
// périmètre des 6 de la base de développement (TEAM_COLORS).
//
// Les deux équipes sont résolues ENSEMBLE (pas deux appels indépendants
// par équipe) car la couleur de l'équipe EXTÉRIEURE dépend de celle du
// DOMICILE : en cas de collision perceptuelle entre les deux primaires
// (teamColorCollision.js), seule l'extérieure bascule sur sa secondaire --
// jamais le domicile, jamais les deux à la fois.
//
// Collision calculée sur les couleurs BRUTES (avant adjustForContrast),
// jamais sur le rendu ajusté -- voir teamColorCollision.js pour le
// raisonnement complet (sinon la bascule primaire/secondaire dépendrait du
// mode clair/sombre).
export function resolveTeamBadges(homeAbbreviation, awayAbbreviation, theme) {
  const home = TEAM_COLORS[homeAbbreviation]
  const away = TEAM_COLORS[awayAbbreviation]
  const background = SURFACE_BY_THEME[theme] ?? SURFACE_BY_THEME.dark

  const collision = Boolean(home) && Boolean(away) && haveColorCollision(home.primary, away.primary)
  const awayRawColor = away ? (collision ? away.secondary : away.primary) : null

  return {
    home: home ? badgeFromRawColor(home.primary, background) : null,
    away: awayRawColor ? badgeFromRawColor(awayRawColor, background) : null,
  }
}
