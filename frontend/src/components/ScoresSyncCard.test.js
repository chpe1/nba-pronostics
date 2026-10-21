import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ScoresSyncCard from './ScoresSyncCard.vue'

// apiClient stubbé : aucun vrai réseau en test de composant (même principe que InjuryUpdateCard.test.js).
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch, ApiError } from '@/services/apiClient'

const BUTTON_LABEL = 'Synchroniser les scores'

const GAME = {
  game_id: 3,
  away_team_name: 'Oklahoma City Thunder',
  away_team_abbreviation: 'OKC',
  home_team_name: 'San Antonio Spurs',
  home_team_abbreviation: 'SAS',
  away_score: 116,
  home_score: 104,
  correction: false,
}

function day(date, overrides = {}) {
  return {
    date,
    found: 0,
    recorded_count: 0,
    already_final_count: 0,
    not_finished_count: 0,
    status_change_count: 0,
    skipped_count: 0,
    recorded: [],
    status_changes: [],
    skipped: [],
    ...overrides,
  }
}

const REPORT = {
  date_from: '2026-10-19',
  date_to: '2026-10-21',
  days_count: 3,
  found: 14,
  recorded_count: 2,
  already_final_count: 1,
  not_finished_count: 10,
  status_change_count: 0,
  skipped_count: 1,
  written: true,
  days: [
    day('2026-10-19'),
    day('2026-10-20', {
      found: 3,
      recorded_count: 2,
      already_final_count: 1,
      recorded: [GAME, { ...GAME, game_id: 2, away_team_name: 'Philadelphia 76ers', home_team_name: 'New York Knicks', away_score: 106, home_score: 100 }],
    }),
    day('2026-10-21', {
      found: 11,
      not_finished_count: 10,
      skipped_count: 1,
      skipped: [{ label: 'MIN @ MIA', reason: 'manually_overridden', reason_label: 'match verrouillé à la main : jamais modifié par la synchro' }],
    }),
  ],
}

const NOTHING = {
  ...REPORT,
  found: 3,
  recorded_count: 0,
  already_final_count: 3,
  not_finished_count: 0,
  skipped_count: 0,
  written: false,
  days: [day('2026-10-19'), day('2026-10-20', { found: 3, already_final_count: 3 }), day('2026-10-21')],
}

const button = (w) => w.findAll('button').find((b) => b.text().includes(BUTTON_LABEL))
const text = (w, id) => w.get(`[data-testid="${id}"]`).text()

beforeEach(() => {
  apiFetch.mockReset()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-21T15:00:00Z'))
})
afterEach(() => vi.useRealTimers())

describe('plage par défaut', () => {
  it("propose les trois derniers jours jusqu'à la date NBA du jour (heure de New York, pas UTC)", () => {
    vi.setSystemTime(new Date('2026-10-22T02:30:00Z')) // 22:30 le 21 à New York : la date NBA est encore le 21
    const wrapper = mount(ScoresSyncCard)
    expect(wrapper.get('[data-testid="scores-date-to"]').element.value).toBe('2026-10-21')
    expect(wrapper.get('[data-testid="scores-date-from"]').element.value).toBe('2026-10-18')
  })
})

describe('compte-rendu', () => {
  async function run(report) {
    apiFetch.mockResolvedValue(report)
    const wrapper = mount(ScoresSyncCard)
    await button(wrapper).trigger('click')
    await flushPromises()
    return wrapper
  }

  it('envoie la plage choisie et affiche le compte-rendu en entier, matchs nommés avec leur score', async () => {
    const wrapper = await run(REPORT)
    const [path, options] = apiFetch.mock.calls[0]
    expect(path).toBe('/api/scores/sync?date_from=2026-10-18&date_to=2026-10-21')
    expect(options.method).toBe('POST')
    expect(text(wrapper, 'scores-found')).toBe('14')
    expect(text(wrapper, 'scores-recorded')).toBe('2')
    expect(text(wrapper, 'scores-already-final')).toBe('1')
    expect(text(wrapper, 'scores-not-finished')).toBe('10')
    expect(text(wrapper, 'scores-skipped')).toBe('1')
    expect(text(wrapper, 'scores-written')).toBe('oui')
    const list = text(wrapper, 'scores-recorded-list')
    expect(list).toContain('Oklahoma City Thunder 116 – 104 San Antonio Spurs')
    expect(list).toContain('Philadelphia 76ers 106 – 100 New York Knicks')
    expect(text(wrapper, 'scores-skipped-list')).toContain('MIN @ MIA')
    expect(text(wrapper, 'scores-skipped-list')).toContain('verrouillé à la main')
    expect(text(wrapper, 'scores-days')).toContain('20/10/2026 : 3 trouvé(s), 2 enregistré(s)')
    expect(wrapper.find('[data-testid="scores-nothing-changed"]').exists()).toBe(false)
  })

  it("dit explicitement quand rien n'a changé (jamais un simple succès)", async () => {
    const wrapper = await run(NOTHING)
    expect(wrapper.get('[data-testid="scores-nothing-changed"]').text()).toContain("Rien n'a changé en base")
    expect(text(wrapper, 'scores-written')).toBe('non')
    expect(text(wrapper, 'scores-recorded')).toBe('0')
    expect(text(wrapper, 'scores-already-final')).toBe('3')
    expect(wrapper.find('[data-testid="scores-recorded-list"]').exists()).toBe(false)
  })

  it("dit que l'API ne renvoie aucun match quand la plage est vide", async () => {
    const wrapper = await run({ ...NOTHING, found: 0, already_final_count: 0, days: [day('2026-10-19'), day('2026-10-20'), day('2026-10-21')] })
    expect(wrapper.get('[data-testid="scores-nothing-changed"]').text()).toContain("aucun match")
  })

  it('signale un score corrigé sur un match déjà terminé', async () => {
    const corrected = { ...REPORT, days: [day('2026-10-20', { found: 1, recorded_count: 1, recorded: [{ ...GAME, correction: true }] })] }
    const wrapper = await run(corrected)
    expect(text(wrapper, 'scores-recorded-list')).toContain('score corrigé')
  })
})

describe('erreur', () => {
  it("affiche le VRAI message du serveur, sans compte-rendu", async () => {
    apiFetch.mockRejectedValue(new ApiError('balldontlie a répondu 429 : Too Many Requests (limite de requêtes atteinte, réessayez dans une minute)'))
    const wrapper = mount(ScoresSyncCard)
    await button(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('balldontlie a répondu 429')
    expect(wrapper.find('[data-testid="scores-report"]').exists()).toBe(false)
  })

  it('refuse sans appel une plage inversée', async () => {
    const wrapper = mount(ScoresSyncCard)
    await wrapper.get('[data-testid="scores-date-from"]').setValue('2026-10-25')
    await button(wrapper).trigger('click')
    await flushPromises()
    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('précéder')
  })
})

describe("attente (Décision n°35) : rien avant 200 ms, 300 ms minimum, libellé jamais remplacé", () => {
  const spinner = (w) => w.find('[data-testid="scores-spinner"]')

  it("réponse rapide : l'indicateur n'apparaît jamais, le libellé reste", async () => {
    apiFetch.mockResolvedValue(NOTHING)
    const wrapper = mount(ScoresSyncCard)
    await button(wrapper).trigger('click')
    await vi.advanceTimersByTimeAsync(50)
    await flushPromises()
    expect(spinner(wrapper).exists()).toBe(false)
    expect(button(wrapper).text()).toContain(BUTTON_LABEL)
  })

  it("réponse lente : l'indicateur apparaît à 200 ms, reste 300 ms au moins, le libellé ne change jamais", async () => {
    let resolve
    apiFetch.mockReturnValue(new Promise((r) => (resolve = r)))
    const wrapper = mount(ScoresSyncCard)
    await button(wrapper).trigger('click')
    await vi.advanceTimersByTimeAsync(150)
    expect(spinner(wrapper).exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(60) // 210 ms
    expect(spinner(wrapper).exists()).toBe(true)
    expect(button(wrapper).text()).toContain(BUTTON_LABEL)
    resolve(NOTHING)
    await vi.advanceTimersByTimeAsync(10)
    expect(spinner(wrapper).exists()).toBe(true) // 300 ms minimum une fois affiché
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(spinner(wrapper).exists()).toBe(false)
    expect(button(wrapper).text()).toContain(BUTTON_LABEL)
  })

  it('un second clic pendant le traitement est ignoré', async () => {
    apiFetch.mockReturnValue(new Promise(() => {}))
    const wrapper = mount(ScoresSyncCard)
    await button(wrapper).trigger('click')
    await button(wrapper).trigger('click')
    expect(apiFetch).toHaveBeenCalledTimes(1)
  })
})
