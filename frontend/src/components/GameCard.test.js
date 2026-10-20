import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameCard from './GameCard.vue'

// L'heure d'un match est celle de New York (Game.game_date, US/ET naïf, limitation n°35) : la carte la dit,
// sans la convertir. Test minimal du libellé ; le rendu du reste de la carte est couvert ailleurs.

const BASE = {
  id: 1,
  season: '2026-2027',
  game_date: '2026-10-20T15:00:00',
  home_team_id: 1,
  home_team_name: 'Detroit Pistons',
  home_team_abbreviation: 'DET',
  away_team_id: 2,
  away_team_name: 'Boston Celtics',
  away_team_abbreviation: 'BOS',
  status: 'scheduled',
  home_score: null,
  away_score: null,
  home_team_recent_record: { wins: 0, losses: 0, games_considered: 0 },
  away_team_recent_record: { wins: 0, losses: 0, games_considered: 0 },
  home_calendar_status: { is_back_to_back: false, is_three_in_four: false },
  away_calendar_status: { is_back_to_back: false, is_three_in_four: false },
  reliability_threshold_low: 7,
  reliability_threshold_high: 30,
  prediction: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
})

describe("libellé de l'heure du match", () => {
  it("dit que l'heure est celle de New York, à côté de l'heure", () => {
    const wrapper = mount(GameCard, { props: { game: BASE } })
    const zone = wrapper.get('[data-testid="game-time-zone"]')
    expect(zone.text()).toContain('New York')
    expect(wrapper.text()).toMatch(/15:00\s*·\s*New York/)
  })

  it("ne convertit pas l'heure : 15:00 reste 15:00 quel que soit le fuseau du navigateur", () => {
    const wrapper = mount(GameCard, { props: { game: { ...BASE, game_date: '2026-10-20T21:30:00' } } })
    expect(wrapper.text()).toMatch(/21:30\s*·\s*New York/)
  })

  it("n'affiche pas le libellé quand le score remplace l'heure (match terminé)", () => {
    const finished = { ...BASE, status: 'finished', home_score: 112, away_score: 105 }
    const wrapper = mount(GameCard, { props: { game: finished } })
    expect(wrapper.find('[data-testid="game-time-zone"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('105-112')
  })
})
