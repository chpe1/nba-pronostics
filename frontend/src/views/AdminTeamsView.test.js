import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'
import AdminTeamsView from './AdminTeamsView.vue'

const team = (id, abbr, diff) => ({
  id,
  name: abbr,
  abbreviation: abbr,
  win_pct_home: 0,
  win_pct_away: 0,
  win_pct_home_prev_season: 0.5,
  win_pct_away_prev_season: 0.5,
  point_diff_prev_season: diff,
  created_at: '2026-10-26T00:00:00',
  updated_at: '2026-10-26T00:00:00',
})

beforeEach(() => apiFetch.mockReset())

describe('écart de points N-1 (écran Équipes)', () => {
  it('affiche la somme des écarts enregistrés et combien sont renseignés', async () => {
    apiFetch.mockResolvedValueOnce([team(1, 'OKC', 11.15), team(2, 'WAS', -11.98), team(3, 'BOS', null)])
    const w = mount(AdminTeamsView)
    await flushPromises()
    const summary = w.get('[data-testid="point-diff-summary"]').text()
    expect(summary).toMatch(/renseigné pour 2 équipes\s+sur 3/)
    expect(summary).toContain('-0.83')
  })

  it("une case vidée envoie null, jamais 0 ; une valeur saisie est envoyée en nombre", async () => {
    apiFetch.mockResolvedValueOnce([team(1, 'OKC', 11.15)])
    const w = mount(AdminTeamsView)
    await flushPromises()
    const input = w.get('#point-diff-1')
    await input.setValue('')
    apiFetch.mockResolvedValueOnce(team(1, 'OKC', null))
    await w.get('button').trigger('click')
    await flushPromises()
    expect(apiFetch.mock.calls[1][1].body.point_diff_prev_season).toBeNull()

    await w.get('#point-diff-1').setValue('-4.5')
    apiFetch.mockResolvedValueOnce(team(1, 'OKC', -4.5))
    await w.get('button').trigger('click')
    await flushPromises()
    expect(apiFetch.mock.calls[2][1].body.point_diff_prev_season).toBe(-4.5)
  })
})

const record = (overrides = {}) => ({
  season: '2026-2027',
  home: { wins: 3, losses: 1, games: 4, pct: 0.75 },
  away: { wins: 0, losses: 0, games: 0, pct: null },
  last_game_date: '2026-10-30',
  stored_matches_recount: true,
  excluded_games: [],
  ...overrides,
})

describe('pourcentages de la saison en cours (calculés, lecture seule)', () => {
  it("n'offre aucun champ de saisie et n'envoie jamais ces deux valeurs", async () => {
    apiFetch.mockResolvedValueOnce([{ ...team(1, 'OKC', 1), win_pct_home: 0.75, win_pct_away: null, current_season_record: record() }])
    const w = mount(AdminTeamsView)
    await flushPromises()
    expect(w.findAll('input[type="number"]')).toHaveLength(3) // N-1 domicile, N-1 extérieur, écart N-1
    apiFetch.mockResolvedValueOnce({ ...team(1, 'OKC', 1), current_season_record: record() })
    await w.get('button').trigger('click')
    await flushPromises()
    const body = apiFetch.mock.calls[1][1].body
    expect(body).not.toHaveProperty('win_pct_home')
    expect(body).not.toHaveProperty('win_pct_away')
  })

  it('affiche le nombre de matchs, le bilan et la date du dernier match ; un côté sans match est vide, jamais 0', async () => {
    apiFetch.mockResolvedValueOnce([{ ...team(1, 'OKC', 1), win_pct_home: 0.75, win_pct_away: null, current_season_record: record() }])
    const w = mount(AdminTeamsView)
    await flushPromises()
    const home = w.get('[data-testid="current-season-1-home"]').text()
    expect(home).toContain('0.750')
    expect(home).toMatch(/sur 4 matchs\s+terminés\s+\(3-1\)/)
    const away = w.get('[data-testid="current-season-1-away"]').text()
    expect(away).toContain('vide (aucun match compté)')
    expect(away).not.toMatch(/0\.000/)
    expect(w.get('[data-testid="current-season-1"]').text()).toContain('Dernier match compté : 30/10/2026')
    expect(w.find('[data-testid="current-season-1-mismatch"]').exists()).toBe(false)
  })

  it('signale visiblement une valeur enregistrée différente du recomptage, et les matchs non comptés', async () => {
    apiFetch.mockResolvedValueOnce([
      {
        ...team(1, 'OKC', 1),
        win_pct_home: 0,
        win_pct_away: 0,
        current_season_record: record({
          stored_matches_recount: false,
          excluded_games: [{ game_id: 9, game_date: '2026-10-28', reason: 'terminé sans score' }],
        }),
      },
    ])
    const w = mount(AdminTeamsView)
    await flushPromises()
    const mismatch = w.get('[data-testid="current-season-1-mismatch"]').text()
    expect(mismatch).toContain('domicile 0.000')
    expect(mismatch).toContain('DIFFÉRENTE du recomptage')
    expect(w.get('[data-testid="current-season-1-excluded"]').text()).toContain('match du 28/10/2026 (terminé sans score)')
  })
})
