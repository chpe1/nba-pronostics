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

describe('plafond de la fiabilité en début de saison', () => {
  const prediction = (capCap) => ({
    id: 1,
    game_id: 1,
    is_upcoming: false,
    home_team_note: 70,
    away_team_note: 20,
    predicted_winner_team_id: 1,
    spread: 50,
    reliability: 'moyenne',
    breakdown: {
      home: { absent_players: [], questionable_players: [] },
      away: { absent_players: [], questionable_players: [] },
      ...(capCap === undefined ? {} : { reliability_cap: capCap }),
    },
    computed_at: '2026-10-21T19:31:37',
  })
  const note = (w) => w.find('[data-testid="reliability-cap-note"]')

  it('dit POURQUOI la confiance est limitée quand le serveur a plafonné l\'étiquette', () => {
    const wrapper = mount(GameCard, {
      props: { game: { ...BASE, prediction: prediction({ capped: true, uncapped: 'forte', reason: 'early_season' }) } },
    })
    expect(note(wrapper).text()).toBe('Confiance limitée : début de saison, notes basées sur la saison précédente.')
    expect(wrapper.text()).toContain('Confiance modérée') // l'étiquette affichée est celle du serveur
  })

  it('ne dit rien quand rien n\'a été plafonné, ni pour un ancien pronostic sans cette information', () => {
    const notCapped = mount(GameCard, {
      props: { game: { ...BASE, prediction: prediction({ capped: false, uncapped: 'moyenne', reason: null }) } },
    })
    expect(note(notCapped).exists()).toBe(false)
    const legacy = mount(GameCard, { props: { game: { ...BASE, prediction: prediction(undefined) } } })
    expect(note(legacy).exists()).toBe(false)
  })

  it('ne l\'affiche pas pour un pronostic non révélé (match trop lointain)', () => {
    const hidden = { ...prediction({ capped: true, uncapped: 'forte', reason: 'early_season' }), is_upcoming: true, breakdown: null }
    const wrapper = mount(GameCard, { props: { game: { ...BASE, prediction: hidden } } })
    expect(note(wrapper).exists()).toBe(false)
  })
})

describe('probabilité de victoire (à côté de la note)', () => {
  const inputs = (homeGames = 3, awayGames = 4, missing = []) => ({
    params: { w: 8, c: 0.7, home_advantage: 1.84, sigma: 14.13 },
    home: { team_id: 1, prev_point_diff: 8.16, games_used: homeGames, margin_sum: 10, force: 6 },
    away: { team_id: 2, prev_point_diff: 7.7, games_used: awayGames, margin_sum: 5, force: 5 },
    missing_prev_point_diff: missing,
  })
  const revealed = (extra = {}, absents = { home: [], away: [] }) => ({
    ...BASE,
    prediction: {
      id: 1,
      game_id: 1,
      is_upcoming: false,
      home_team_note: 70,
      away_team_note: 60,
      predicted_winner_team_id: 1,
      spread: 10,
      reliability: 'moyenne',
      breakdown: {
        home: { absent_players: absents.home, questionable_players: [] },
        away: { absent_players: absents.away, questionable_players: [] },
      },
      probability_model_version: 'ecart1/w=8/c=0.7/hca=1.84/sigma=14.13',
      expected_margin: 2.6,
      home_win_probability: 0.573,
      probability_inputs: inputs(),
      computed_at: '2026-10-26T19:00:00',
      ...extra,
    },
  })
  const block = (w) => w.get('[data-testid="win-probability"]')
  const find = (w, id) => w.find(`[data-testid="win-probability-${id}"]`)

  it('affiche les deux probabilités dans un bloc distinct de la note, et les matchs utilisés', () => {
    const w = mount(GameCard, { props: { game: revealed() } })
    expect(block(w).text()).toContain('distinct de la note')
    // Chaque équipe et son pourcentage sont deux éléments distincts (l'espace entre eux est portée par la mise
    // en page : un texte collé « BOS43 % » ne serait pas attrapé par une simple lecture du texte de la carte).
    const pairs = find(w, 'values').findAll(':scope > span').map((s) => s.findAll('span').map((x) => x.text()))
    expect(pairs).toEqual([['BOS', '43 %'], ['DET', '57 %']])
    expect(find(w, 'games').text()).toContain('BOS 4')
    expect(find(w, 'games').text()).toContain('DET 3')
    expect(find(w, 'unmeasured').exists()).toBe(false)
    expect(find(w, 'absents').exists()).toBe(false)
  })

  it("n'affiche aucune cote ni value : seulement des probabilités", () => {
    const text = block(mount(GameCard, { props: { game: revealed() } })).text().toLowerCase()
    for (const word of ['cote', 'value', 'pari', 'mise']) expect(text).not.toContain(word)
  })

  it('porte la mention « non mesuré » dès que la probabilité AFFICHÉE atteint 90 %, des deux côtés', () => {
    expect(find(mount(GameCard, { props: { game: revealed({ home_win_probability: 0.896 }) } }), 'unmeasured').exists()).toBe(true)
    expect(find(mount(GameCard, { props: { game: revealed({ home_win_probability: 0.08 }) } }), 'unmeasured').exists()).toBe(true)
    expect(find(mount(GameCard, { props: { game: revealed({ home_win_probability: 0.894 }) } }), 'unmeasured').exists()).toBe(false)
  })

  it('dit que les absents sont ignorés, avec leur nombre sur les deux équipes', () => {
    const absents = { home: [{ name: 'A', per: 20 }], away: [{ name: 'B', per: 15 }, { name: 'C', per: 12 }] }
    const w = mount(GameCard, { props: { game: revealed({}, absents) } })
    expect(find(w, 'absents').text()).toMatch(/Ne tient pas compte des absents : 3\s+joueurs\s+absents/)
    const one = mount(GameCard, { props: { game: revealed({}, { home: [{ name: 'A', per: 20 }], away: [] }) } })
    expect(find(one, 'absents').text()).toMatch(/1\s+joueur\s+absent\s+sur/)
  })

  it("écart N-1 manquant : pas de pourcentage, et l'équipe en cause est nommée (jamais un 0)", () => {
    const w = mount(GameCard, {
      props: { game: revealed({ home_win_probability: null, expected_margin: null, probability_inputs: inputs(0, 0, [2]) }) },
    })
    expect(find(w, 'values').exists()).toBe(false)
    expect(find(w, 'missing').text()).toContain('non renseigné pour BOS')
    expect(block(w).text()).not.toMatch(/\d+ %/)
  })

  it('ancien pronostic sans probabilité : le dit, sans inventer de chiffre', () => {
    const legacy = revealed({ home_win_probability: undefined, expected_margin: undefined, probability_inputs: undefined, probability_model_version: undefined })
    const w = mount(GameCard, { props: { game: legacy } })
    expect(find(w, 'legacy').exists()).toBe(true)
    expect(find(w, 'games').exists()).toBe(false)
  })

  it("n'affiche rien pour un pronostic non révélé (match trop lointain)", () => {
    const hidden = { ...BASE, prediction: { id: 1, game_id: 1, is_upcoming: true, computed_at: '2026-10-21T19:31:37' } }
    expect(mount(GameCard, { props: { game: hidden } }).find('[data-testid="win-probability"]').exists()).toBe(false)
  })
})
