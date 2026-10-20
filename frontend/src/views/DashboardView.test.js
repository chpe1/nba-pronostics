import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DashboardView from './DashboardView.vue'
import { useAuthStore } from '@/stores/auth'

// Recalcul du tableau de bord et matchs terminés : le serveur ignore ces matchs (leur pronostic d'avant-match
// est la seule trace de ce qui avait été annoncé) et l'écran DOIT le dire, avec leur nom. apiClient stubbé.
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'

const SKIPPED = [
  { game_id: 1, home_team_name: 'Detroit Pistons', home_team_abbreviation: 'DET', away_team_name: 'Boston Celtics', away_team_abbreviation: 'BOS' },
]

let recalcResponse

async function mountDashboard() {
  setActivePinia(createPinia())
  useAuthStore().token = 'jeton-de-test' // le bouton n'apparaît que connecté ; état du store, pas un vrai jeton
  apiFetch.mockImplementation((path, options = {}) => {
    if (options.method === 'POST') return Promise.resolve(recalcResponse)
    return Promise.resolve([])
  })
  const wrapper = mount(DashboardView)
  await flushPromises()
  return wrapper
}

const recalcButton = (w) => w.findAll('button').find((b) => b.text().includes('Recalculer'))
const notice = (w) => w.find('[data-testid="skipped-finished"]')

// jsdom n'implémente pas scrollIntoView (la bande de dates l'appelle au montage) : stub, comme pour requestAnimationFrame.
beforeEach(() => {
  apiFetch.mockReset()
  Element.prototype.scrollIntoView = vi.fn()
})

describe('recalcul : matchs terminés ignorés', () => {
  it('nomme le match terminé ignoré (jamais un silence)', async () => {
    recalcResponse = { predictions: [], skipped_finished_count: 1, skipped_finished: SKIPPED }
    const wrapper = await mountDashboard()
    await recalcButton(wrapper).trigger('click')
    await flushPromises()
    expect(notice(wrapper).exists()).toBe(true)
    expect(notice(wrapper).text()).toContain("1 match terminé n'a pas été recalculé")
    expect(notice(wrapper).text()).toContain('Boston Celtics @ Detroit Pistons')
    expect(notice(wrapper).text()).toContain("pronostic d'avant-match est conservé")
  })

  it('met au pluriel et nomme chaque match quand il y en a plusieurs', async () => {
    recalcResponse = {
      predictions: [],
      skipped_finished_count: 2,
      skipped_finished: [...SKIPPED, { ...SKIPPED[0], game_id: 2, home_team_name: 'New York Knicks', away_team_name: 'Philadelphia 76ers' }],
    }
    const wrapper = await mountDashboard()
    await recalcButton(wrapper).trigger('click')
    await flushPromises()
    expect(notice(wrapper).text()).toContain("2 matchs terminés n'ont pas été recalculés")
    expect(notice(wrapper).text()).toContain('Philadelphia 76ers @ New York Knicks')
  })

  it("n'affiche rien quand aucun match terminé n'a été ignoré", async () => {
    recalcResponse = { predictions: [], skipped_finished_count: 0, skipped_finished: [] }
    const wrapper = await mountDashboard()
    await recalcButton(wrapper).trigger('click')
    await flushPromises()
    expect(notice(wrapper).exists()).toBe(false)
  })

  it('un nouveau recalcul sans match ignoré efface le message précédent', async () => {
    recalcResponse = { predictions: [], skipped_finished_count: 1, skipped_finished: SKIPPED }
    const wrapper = await mountDashboard()
    await recalcButton(wrapper).trigger('click')
    await flushPromises()
    expect(notice(wrapper).exists()).toBe(true)
    recalcResponse = { predictions: [], skipped_finished_count: 0, skipped_finished: [] }
    await recalcButton(wrapper).trigger('click')
    await flushPromises()
    expect(notice(wrapper).exists()).toBe(false)
  })
})
