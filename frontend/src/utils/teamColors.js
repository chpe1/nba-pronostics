import { TEAM_COLORS } from '@/constants/teamColors'
import { adjustForContrast } from './teamColorContrast'

// Miroir de --surface (style.css, §5.2/§5.3) par mode -- fond réel sur
// lequel le filet d'équipe se pose dans GameCard.vue (bg-surface, jamais
// bg-canvas). Dupliqué à dessein plutôt que lu via getComputedStyle : même
// pattern déjà en place dans ce projet pour le meta theme-color
// (stores/theme.js, dupliqué avec index.html) -- à TENIR À JOUR si
// --surface change de valeur dans style.css.
const SURFACE_BY_THEME = {
  dark: '#1a1d26',
  light: '#ffffff',
}

// Couleur du filet d'équipe (GameCard.vue), ajustée pour rester visible sur
// bg-surface dans le mode donné -- null si l'équipe n'est pas encore dans
// TEAM_COLORS (24 équipes restantes, périmètre non encore étendu, voir
// constants/teamColors.js).
export function teamRailColor(abbreviation, theme) {
  const raw = TEAM_COLORS[abbreviation]
  if (!raw) return null
  const background = SURFACE_BY_THEME[theme] ?? SURFACE_BY_THEME.dark
  return adjustForContrast(raw, background)
}
