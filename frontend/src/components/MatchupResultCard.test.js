import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MatchupResultCard from './MatchupResultCard.vue'

const team = (overrides = {}) => ({
  team_id: 1,
  team_name: 'Atlanta Hawks',
  is_home: false,
  in_early_season: true,
  note_de_base: 0.5,
  injury_penalty: 0,
  absent_players: [],
  questionable_players: [],
  calendar_penalty: 0,
  is_back_to_back: false,
  is_three_in_four: false,
  draft_bonus: 8,
  draft_bonus_raw: 13.15,
  draft_bonus_cap: 8,
  draft_bonus_capped: true,
  draft_players: [
    { name: 'Kingston Flemings', rank: 8, points: 7.05 },
    { name: 'Zuby Ejiofor', rank: 23, points: 5.02 },
    { name: 'Henri Veesaar', rank: 52, points: 1.08 },
  ],
  transfer_adjustment: 0,
  final_note: 58,
  ...overrides,
})

const mountCard = (home, away, extra = {}) =>
  mount(MatchupResultCard, {
    props: { title: 'Résultat réel', predictedWinnerTeamId: 1, spread: 4.4, reliability: 'faible', home, away, ...extra },
  })

describe('détail du bonus draft (plafond par équipe)', () => {
  it('montre le plafond appliqué, la somme avant plafonnement et chaque joueur', () => {
    const wrapper = mountCard(team({ team_id: 2, team_name: 'Orlando Magic', is_home: true, draft_bonus_capped: false, draft_bonus: 1.22, draft_bonus_raw: 1.22, draft_players: [{ name: 'Izaiyah Nelson', rank: 51, points: 1.22 }] }), team())
    const capped = wrapper.findAll('[data-testid="draft-capped"]')
    expect(capped).toHaveLength(1) // seulement Atlanta : Orlando n'est pas plafonnée
    expect(capped[0].text()).toContain('plafonné à 8.00')
    expect(capped[0].text()).toContain('somme 13.15')
    const lists = wrapper.findAll('[data-testid="draft-players"]')
    expect(lists[1].text()).toContain('Kingston Flemings — choix n°8 : 7.05')
    expect(lists[1].text()).toContain('Henri Veesaar — choix n°52 : 1.08')
    expect(lists[0].text()).toContain('Izaiyah Nelson — choix n°51 : 1.22')
  })

  it('reste lisible pour un ancien pronostic sans ce détail', () => {
    const legacy = team({ draft_bonus_capped: undefined, draft_bonus_raw: undefined, draft_bonus_cap: undefined, draft_players: undefined })
    const wrapper = mountCard(legacy, { ...legacy, team_id: 2, is_home: true })
    expect(wrapper.find('[data-testid="draft-capped"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="draft-players"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Bonus draft')
  })
})

describe('crédit des joueurs sans saison N-1', () => {
  it('nomme chaque joueur crédité avec son PER, son MPG et ses points', () => {
    const credited = team({
      no_prev_season_credit: 7.8,
      no_prev_season_players: [{ name: 'Tyrese Haliburton', per: 19.5, mpg: 33, injury_status: 'questionable', points: 7.8 }],
    })
    const wrapper = mountCard(credited, team({ team_id: 2 }))
    expect(wrapper.get('[data-testid="no-prev-credit"]').text()).toBe('7.8')
    const list = wrapper.get('[data-testid="no-prev-players"]').text()
    expect(list).toContain('Tyrese Haliburton — PER 19.5, MPG 33.0 : +7.80')
    expect(list).toContain('(questionable)')
  })

  it('reste lisible pour un ancien pronostic sans ce détail', () => {
    const wrapper = mountCard(team(), team({ team_id: 2 }))
    expect(wrapper.get('[data-testid="no-prev-credit"]').text()).toBe('0.0')
    expect(wrapper.find('[data-testid="no-prev-players"]').exists()).toBe(false)
  })
})

describe('fiabilité plafonnée', () => {
  it('explique le plafonnement quand il a eu lieu', () => {
    const wrapper = mountCard(team(), team({ team_id: 2 }), { reliability: 'moyenne', reliabilityCap: { capped: true, uncapped: 'forte', reason: 'early_season' } })
    const detail = wrapper.get('[data-testid="reliability-cap-detail"]').text()
    expect(detail).toContain('« Forte »')
    expect(detail).toContain('limitée à « Moyenne »')
  })

  it("n'explique rien sans plafonnement", () => {
    const wrapper = mountCard(team(), team({ team_id: 2 }), { reliabilityCap: { capped: false, uncapped: 'moyenne', reason: null } })
    expect(wrapper.find('[data-testid="reliability-cap-detail"]').exists()).toBe(false)
    expect(mountCard(team(), team({ team_id: 2 })).find('[data-testid="reliability-cap-detail"]').exists()).toBe(false)
  })
})
