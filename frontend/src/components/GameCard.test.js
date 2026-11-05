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

describe('mesure sur laquelle repose la note (bascule au 11e match, bases différentes)', () => {
  const withBasis = (homeEarly, awayEarly, extra = {}) => ({
    ...BASE,
    prediction: {
      id: 1,
      game_id: 1,
      is_upcoming: false,
      home_team_note: 70,
      away_team_note: 20,
      predicted_winner_team_id: 1,
      spread: 50,
      reliability: 'moyenne',
      breakdown: {
        home: { absent_players: [], questionable_players: [], in_early_season: homeEarly },
        away: { absent_players: [], questionable_players: [], in_early_season: awayEarly },
        ...extra,
      },
      computed_at: '2026-11-07T19:00:00',
    },
  })
  const switchNote = (w) => w.find('[data-testid="basis-switch-note"]')
  const mixedNote = (w) => w.find('[data-testid="basis-mixed-note"]')

  it('ne dit rien tant que les deux équipes sont sur la saison précédente', () => {
    const w = mount(GameCard, { props: { game: withBasis(true, true) } })
    expect(switchNote(w).exists()).toBe(false)
    expect(mixedNote(w).exists()).toBe(false)
  })

  it("quand une seule a basculé : UNE phrase dit qui est sur quelle mesure, bascule comprise (pas de paragraphe en double)", () => {
    const w = mount(GameCard, { props: { game: withBasis(false, true) } }) // DET (domicile) a basculé, BOS non
    expect(mixedNote(w).text()).toBe(
      "Les deux équipes ne sont pas évaluées sur la même base : BOS sur la saison précédente, DET sur la saison en cours depuis son 11e match. L'écart compare deux mesures différentes.",
    )
    expect(switchNote(w).exists()).toBe(false)
  })

  it("nomme l'équipe de l'extérieur quand c'est elle qui a basculé", () => {
    const w = mount(GameCard, { props: { game: withBasis(true, false) } })
    expect(mixedNote(w).text()).toContain('DET sur la saison précédente, BOS sur la saison en cours depuis son 11e match')
  })

  it('quand les deux ont basculé : une mention au pluriel, et PAS de « bases différentes »', () => {
    const w = mount(GameCard, { props: { game: withBasis(false, false) } })
    expect(switchNote(w).text()).toBe('BOS et DET : note basée sur la saison en cours depuis leur 11e match.')
    expect(mixedNote(w).exists()).toBe(false)
  })

  it("ne devine rien pour un ancien pronostic sans l'information, ni pour un pronostic non révélé", () => {
    const legacy = withBasis(undefined, undefined)
    expect(mixedNote(mount(GameCard, { props: { game: legacy } })).exists()).toBe(false)
    expect(switchNote(mount(GameCard, { props: { game: legacy } })).exists()).toBe(false)
    const hidden = { ...BASE, prediction: { id: 1, game_id: 1, is_upcoming: true, computed_at: '2026-11-07T19:00:00' } }
    expect(switchNote(mount(GameCard, { props: { game: hidden } })).exists()).toBe(false)
  })
})

describe("plafond tenu jusqu'à 40 matchs : un motif qui dit la vérité", () => {
  const capped = (cap, flags = { home: false, away: false }) => ({
    ...BASE,
    prediction: {
      id: 1,
      game_id: 1,
      is_upcoming: false,
      home_team_note: 70,
      away_team_note: 20,
      predicted_winner_team_id: 1,
      spread: 50,
      reliability: 'moyenne',
      breakdown: {
        home: { absent_players: [], questionable_players: [], in_early_season: flags.home },
        away: { absent_players: [], questionable_players: [], in_early_season: flags.away },
        reliability_cap: cap,
      },
      computed_at: '2026-11-09T19:00:00',
    },
  })
  const note = (w) => w.get('[data-testid="reliability-cap-note"]').text()

  it("« peu de matchs de la saison en cours » quand les deux ont basculé mais qu'une a moins de 40 matchs", () => {
    const w = mount(GameCard, {
      props: { game: capped({ capped: true, uncapped: 'forte', reason: 'few_games', games_threshold: 40, fewest_games: 14 }) },
    })
    expect(note(w)).toBe(
      'Confiance limitée : la note repose sur peu de matchs de la saison en cours (moins de 40 pour au moins une des deux équipes).',
    )
    expect(note(w)).not.toContain('saison précédente') // faux à ce stade : ne doit JAMAIS apparaître
  })

  it("reprend le seuil envoyé par le serveur plutôt qu'un 40 codé en dur", () => {
    const w = mount(GameCard, {
      props: { game: capped({ capped: true, uncapped: 'forte', reason: 'few_games', games_threshold: 25, fewest_games: 14 }) },
    })
    expect(note(w)).toContain('moins de 25')
  })

  it('début de saison, une équipe a déjà basculé : ne prétend pas que les DEUX notes viennent de la saison précédente', () => {
    const w = mount(GameCard, {
      props: {
        game: capped(
          { capped: true, uncapped: 'forte', reason: 'early_season', games_threshold: 40, fewest_games: 7 },
          { home: false, away: true },
        ),
      },
    })
    // Le détail (qui est sur quelle mesure) est dans la phrase « bases différentes » : le plafond ne le répète pas.
    expect(note(w)).toBe('Confiance limitée : début de saison.')
    expect(note(w)).not.toContain('saison précédente') // plus de redite, et jamais de « notes basées sur la saison précédente »
  })

  it('les deux équipes en début de saison : le texte historique, inchangé', () => {
    const w = mount(GameCard, {
      props: {
        game: capped(
          { capped: true, uncapped: 'forte', reason: 'early_season', games_threshold: 40, fewest_games: 3 },
          { home: true, away: true },
        ),
      },
    })
    expect(note(w)).toBe('Confiance limitée : début de saison, notes basées sur la saison précédente.')
  })
})

describe('liste complète des faits de contexte (pastille « +N » cliquable)', () => {
  const players = (prefix, n) => Array.from({ length: n }, (_, i) => ({ name: `${prefix}${i + 1}`, per: 15, reason: null }))
  // Domicile : 1 absent + 3 incertains + B2B + 3-en-4 = 6 faits (deux pastilles + « +4 ») ; extérieur : 1 seul fait.
  const game = (homeAbsent = 1, homeQuestionable = 3) => ({
    ...BASE,
    home_calendar_status: { is_back_to_back: true, is_three_in_four: true },
    away_calendar_status: { is_back_to_back: true, is_three_in_four: false },
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
        home: { absent_players: players('Abs', homeAbsent), questionable_players: players('Inc', homeQuestionable) },
        away: { absent_players: [], questionable_players: [] },
      },
      computed_at: '2026-10-21T19:31:37',
    },
  })
  const toggle = (w) => w.find('[data-testid="facts-toggle-home"]')
  const panel = (w) => w.find('[data-testid="facts-panel"]')

  it('rend le « +N » en vrai bouton, fermé par défaut, avec un libellé qui dit ce qu\'il fait', () => {
    const w = mount(GameCard, { props: { game: game() } })
    const b = toggle(w)
    expect(b.exists()).toBe(true)
    expect(b.element.tagName).toBe('BUTTON')
    expect(b.attributes('type')).toBe('button')
    expect(b.text()).toBe('+4')
    expect(b.attributes('aria-expanded')).toBe('false')
    expect(b.attributes('aria-label')).toBe('+4, afficher le détail complet de DET')
    expect(panel(w).exists()).toBe(false)
  })

  it('ne met aucun bouton sur une équipe dont tous les faits tiennent dans la carte fermée', () => {
    const w = mount(GameCard, { props: { game: game() } })
    expect(w.find('[data-testid="facts-toggle-away"]').exists()).toBe(false)
  })

  it('au clic, montre TOUS les faits (rien de caché), puis un second clic referme', async () => {
    const w = mount(GameCard, { props: { game: game() } })
    await toggle(w).trigger('click')
    expect(toggle(w).attributes('aria-expanded')).toBe('true')
    expect(toggle(w).text()).toBe('Masquer')
    expect(toggle(w).attributes('aria-label')).toBe('Masquer le détail de DET')
    expect(toggle(w).attributes('aria-controls')).toBe(panel(w).attributes('id'))
    const texts = w.findAll('[data-testid="fact-pill"]').map((p) => p.text())
    expect(texts).toEqual(['Abs1 absent', 'B2B', '3-en-4', 'Inc1 incertain', 'Inc2 incertain', 'Inc3 incertain'])
    await toggle(w).trigger('click')
    expect(toggle(w).attributes('aria-expanded')).toBe('false')
    expect(panel(w).exists()).toBe(false)
    expect(w.text()).toContain('+4')
  })

  it('range les faits en groupes dont le titre dit, avec le compte, s\'ils pèsent sur la note', async () => {
    const w = mount(GameCard, { props: { game: game(2, 3) } })
    await toggle(w).trigger('click')
    const title = (kind) => w.get(`[data-testid="facts-group-${kind}"] p`).text()
    expect(title('absent')).toBe('Absents, pèsent sur la note (2)')
    expect(title('calendar')).toBe('Calendrier, pèse sur la note (2)')
    expect(title('questionable')).toBe('Incertains, sans effet sur la note (3)')
  })

  it('porte la distinction par le remplissage : pleine si ça pèse, contour pointillé sans fond sinon ; la teinte ne change pas', async () => {
    const w = mount(GameCard, { props: { game: game() } })
    await toggle(w).trigger('click')
    const cls = (kind) => w.get(`[data-kind="${kind}"]`).classes()
    // Ce qui pèse : fond plein, teinte inchangée (rouge pour un joueur, ambre pour le calendrier).
    expect(cls('absent')).toEqual(expect.arrayContaining(['bg-danger/15', 'text-danger-text']))
    expect(cls('calendar')).toEqual(expect.arrayContaining(['bg-warning/15', 'text-warning-on-tint']))
    // Ce qui ne pèse pas : contour pointillé, AUCUN fond.
    const q = cls('questionable')
    expect(q).toEqual(expect.arrayContaining(['border-dashed', 'border-warning', 'text-warning']))
    expect(q.some((c) => c.startsWith('bg-'))).toBe(false)
    // Les pastilles pleines n'ont ni contour visible ni pointillé.
    expect(cls('absent')).not.toContain('border-dashed')
    expect(cls('calendar')).not.toContain('border-dashed')
  })

  it('n\'ouvre rien tant qu\'il n\'y a pas de clic : aucun gestionnaire de survol sur le bouton', () => {
    const w = mount(GameCard, { props: { game: game() } })
    expect(panel(w).exists()).toBe(false)
    const html = toggle(w).html()
    expect(html).not.toMatch(/mouseenter|mouseover|onmouse/i)
  })

  it("nomme l'équipe en tête du panneau, et en fait le nom de la région (aria-labelledby)", async () => {
    const w = mount(GameCard, { props: { game: game() } })
    await toggle(w).trigger('click')
    const region = panel(w)
    expect(region.attributes('role')).toBe('region')
    const label = w.get(`#${region.attributes('aria-labelledby')}`)
    expect(label.text()).toBe('DET')
    expect(w.get('[data-testid="facts-team"]').element).toBe(label.element)
    // pas d'abréviation répétée dans les titres de groupe
    expect(w.get('[data-testid="facts-group-absent"] p').text()).not.toContain('DET')
  })
})
