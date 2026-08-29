import { defineStore } from 'pinia'

const STORAGE_KEY = 'nba-pronostics-theme'

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
  // Même mapping que le script bloquant d'index.html (dupliqué à dessein :
  // ce script-ci ne s'exécute qu'une fois avant le premier rendu, celui-là
  // doit aussi réagir à une bascule après coup).
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'light' ? '#F4F5F7' : '#0E1015')
}

// La lecture localStorage + la pose de data-theme avant le premier rendu se
// fait dans index.html (script bloquant, pour éviter un éclair de thème
// clair au chargement) -- ce store lit simplement l'attribut déjà posé
// comme état initial, pour n'avoir qu'un seul endroit qui décide de la
// valeur par défaut.
function initialTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: initialTheme(),
  }),

  actions: {
    setTheme(theme) {
      this.theme = theme
      applyTheme(theme)
      try {
        localStorage.setItem(STORAGE_KEY, theme)
      } catch {
        // Stockage indisponible (navigation privée, quota) : le thème reste
        // appliqué pour cette session, simplement pas mémorisé pour la
        // prochaine visite. Pas un réglage serveur (docs/design-v1.md §7).
      }
    },

    toggleTheme() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
  },
})
