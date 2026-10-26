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
