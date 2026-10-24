import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AdminOddsView from './AdminOddsView.vue'

vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'

const emptyCell = () => ({ value: null, recorded_at: null })

const GAME = {
  id: 1,
  game_date: '2026-10-24T19:00:00',
  home_team_name: 'Boston Celtics',
  home_team_abbreviation: 'BOS',
  away_team_name: 'Miami Heat',
  away_team_abbreviation: 'MIA',
  started: false,
  winamax_home: emptyCell(),
  winamax_away: emptyCell(),
  unibet_home: emptyCell(),
  unibet_away: emptyCell(),
}

const STARTED_GAME = { ...GAME, id: 2, started: true, away_team_abbreviation: 'LAL', home_team_abbreviation: 'DET' }

let postCalls

function stubApi(games = [GAME]) {
  postCalls = []
  apiFetch.mockImplementation((path, options = {}) => {
    if (options.method === 'POST' && path === '/api/odds') {
      postCalls.push(options.body)
      const entries = options.body.entries.map((e) => ({ ...e, outcome: 'created', detail: null }))
      return Promise.resolve({
        created_count: entries.length, updated_count: 0, unchanged_count: 0, skipped_count: 0, rejected_count: 0,
        entries,
      })
    }
    if (path.startsWith('/api/odds')) return Promise.resolve({ date: '2026-10-24', games })
    throw new Error(`chemin inattendu : ${path}`)
  })
}

async function mountView() {
  const wrapper = mount(AdminOddsView)
  await flushPromises()
  return wrapper
}

beforeEach(() => stubApi())

describe('AdminOddsView', () => {
  it('affiche les quatre champs par match, vides sans cote enregistrée', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[data-testid="cell-1-winamax_home"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cell-1-winamax_home"]').element.value).toBe('')
  })

  it('pré-remplit une cellule déjà connue, au format français', async () => {
    const withValue = { ...GAME, winamax_home: { value: 1.85, recorded_at: '2026-10-24T14:00:00Z' } }
    stubApi([withValue])
    const wrapper = await mountView()
    expect(wrapper.find('[data-testid="cell-1-winamax_home"]').element.value).toBe('1,85')
  })

  it("l'ordre de tabulation suit la colonne, pas la ligne (deux matchs)", async () => {
    const game2 = { ...GAME, id: 3, away_team_abbreviation: 'ORL', home_team_abbreviation: 'NYK' }
    stubApi([GAME, game2])
    const wrapper = await mountView()
    const tab = (id, col) => Number(wrapper.find(`[data-testid="cell-${id}-${col}"]`).attributes('tabindex'))
    // match 1 puis match 2 de la colonne winamax_home (tabindex 2 et 3), AVANT winamax_away (4 et 5) :
    // la colonne entière se termine avant la colonne suivante ne commence.
    expect(tab(1, 'winamax_home')).toBeLessThan(tab(3, 'winamax_home'))
    expect(tab(3, 'winamax_home')).toBeLessThan(tab(1, 'winamax_away'))
    expect(tab(1, 'winamax_away')).toBeLessThan(tab(3, 'winamax_away'))
    expect(tab(3, 'winamax_away')).toBeLessThan(tab(1, 'unibet_home'))
  })

  it("un match déjà commencé n'est pas saisissable, avec une explication visible", async () => {
    stubApi([STARTED_GAME])
    const wrapper = await mountView()
    const input = wrapper.find('[data-testid="cell-2-winamax_home"]')
    expect(input.element.disabled).toBe(true)
    expect(wrapper.find('[data-testid="started-explanation"]').text()).toContain("Coup d'envoi")
  })

  it('les cases vides sont ignorées : seule la case remplie est envoyée', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-testid="cell-1-winamax_home"]').setValue('1,85')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(postCalls[0].entries).toEqual([{ game_id: 1, side: 'home', source: 'winamax', value: '1,85' }])
  })

  it('accepte la virgule ET le point sans erreur', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-testid="cell-1-winamax_home"]').setValue('1,85')
    await wrapper.find('[data-testid="cell-1-winamax_away"]').setValue('2.10')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const values = postCalls[0].entries.map((e) => e.value)
    expect(values).toEqual(['1,85', '2.10'])
  })

  it('affiche la marge du bookmaker et la meilleure cote en direct, sans rien envoyer au serveur', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-testid="cell-1-winamax_home"]').setValue('1,85')
    await wrapper.find('[data-testid="cell-1-winamax_away"]').setValue('1,95')
    const text = wrapper.text()
    expect(text).toContain('Marge winamax')
    expect(postCalls.length).toBe(0) // aucun calcul de value, rien n'est parti au serveur par la saisie seule
  })

  it('Entrée dans un champ enregistre directement (soumission native du formulaire)', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-testid="cell-1-winamax_home"]').setValue('1,85')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(postCalls.length).toBe(1)
  })

  it('affiche le motif de refus sous la cellule concernée, sans perdre les autres', async () => {
    apiFetch.mockImplementation((path, options = {}) => {
      if (options.method === 'POST') {
        return Promise.resolve({
          created_count: 1, updated_count: 0, unchanged_count: 0, skipped_count: 0, rejected_count: 1,
          entries: [
            { game_id: 1, side: 'home', source: 'winamax', outcome: 'created', detail: null },
            { game_id: 1, side: 'away', source: 'winamax', outcome: 'rejected', detail: 'Cote invalide (0.5).' },
          ],
        })
      }
      return Promise.resolve({ date: '2026-10-24', games: [GAME] })
    })
    const wrapper = await mountView()
    await wrapper.find('[data-testid="cell-1-winamax_home"]').setValue('1,85')
    await wrapper.find('[data-testid="cell-1-winamax_away"]').setValue('0,5')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Cote invalide (0.5).')
  })
})
