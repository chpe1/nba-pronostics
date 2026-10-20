import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InjuryUpdateCard from './InjuryUpdateCard.vue'

// apiClient stubbé : aucun vrai réseau en test de composant (même principe que CsvUploadForm.test.js).
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch, ApiError } from '@/services/apiClient'

const BUTTON_LABEL = 'Mettre à jour les blessures depuis la NBA'

const REPORT = {
  report_url: 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-04-08_03_45PM.pdf',
  report_time_new_york: '08/04/2026 15:45 (heure de New York, UTC-04:00)',
  report_time_paris: '08/04/2026 21:45 (heure de Paris, UTC+02:00)',
  game_dates: ['2026-04-08', '2026-04-09'],
  entries_read: 78,
  not_yet_submitted: false,
  not_yet_submitted_count: 0,
  written: true,
  matched_count: 2,
  unmatched_count: 2,
  unmatched: [
    {
      player_name_raw: 'Bryant,Thomas',
      team_abbreviation: 'CLE',
      team_raw: 'ClevelandCavaliers',
      status_raw: 'Out',
      reason: 'Injury',
      exists_in_database_on_teams: ['BOS'],
    },
    {
      player_name_raw: 'Gilbert,Keshon',
      team_abbreviation: 'ATL',
      team_raw: 'AtlantaHawks',
      status_raw: 'Questionable',
      reason: 'Injury',
      exists_in_database_on_teams: [],
    },
    {
      player_name_raw: 'Detached,Dan',
      team_abbreviation: 'LAL',
      team_raw: 'LosAngelesLakers',
      status_raw: 'Out',
      reason: 'Injury',
      exists_in_database_on_teams: [],
      exists_in_database_as_free_agent: true,
    },
  ],
  status_counts: { out: 1, questionable: 1 },
  absent_count: 1,
  mpg_threshold: 15,
  weighing_count: 1,
  weighing: [{ name: 'Jock Landale', team_abbreviation: 'ATL', status: 'out', per: 14, mpg: 25 }],
}

const NOT_SUBMITTED = {
  ...REPORT,
  report_url: 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-19_02_30PM.pdf',
  game_dates: ['2026-10-20'],
  entries_read: 0,
  not_yet_submitted: true,
  not_yet_submitted_count: 6,
  written: false,
  matched_count: 0,
  unmatched_count: 0,
  unmatched: [],
  status_counts: {},
  absent_count: 0,
  weighing_count: 0,
  weighing: [],
}

function button(wrapper) {
  return wrapper.get('button')
}

beforeEach(() => {
  apiFetch.mockReset()
})

describe('InjuryUpdateCard -- compte-rendu', () => {
  it("affiche le compte-rendu complet : rapport, heures, dates, comptes, absents et noms non rattachés", async () => {
    apiFetch.mockResolvedValue(REPORT)
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledWith('/api/injuries/refresh', { method: 'POST' })
    const text = wrapper.text()
    expect(text).toContain(REPORT.report_url)
    expect(text).toContain('08/04/2026 15:45 (heure de New York, UTC-04:00)')
    expect(text).toContain('08/04/2026 21:45 (heure de Paris, UTC+02:00)')
    expect(text).toContain('08/04/2026, 09/04/2026')
    expect(text).toContain('78')
    expect(text).toContain('Out : 1')
    expect(text).toContain('Questionable : 1')
    expect(text).toContain('Jock Landale (ATL)')
    // Les noms non rattachés sont visibles d'emblée (aucun repli à ouvrir), avec l'équipe du rapport
    // et celle de la base quand elle diffère.
    expect(text).toContain('Bryant,Thomas — CLE')
    expect(text).toContain('en base sous : BOS')
    expect(text).toContain('Gilbert,Keshon — ATL')
    expect(text).toContain('Dont 1 existent en base mais sous une autre')
    // Deux cas DISTINCTS : un agent libre n'a pas été « transféré sans que la base le sache »
    expect(text).toContain('Dont 1 existent en base comme agent(s) libre(s)')
    expect(text).toContain('Detached,Dan — LAL')
    expect(text).toContain('en base comme agent libre')
    const summary = wrapper.get('[data-testid="unmatched-summary"]').text()
    expect(summary.match(/transféré sans que la base le sache/g)).toHaveLength(1)
    expect(text).not.toContain('Rapport non encore soumis')
  })

  it("signale un rapport « non encore soumis » sans le faire passer pour « aucun blessé »", async () => {
    apiFetch.mockResolvedValue(NOT_SUBMITTED)
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Rapport non encore soumis')
    expect(text).toContain('20/10/2026')
    expect(text).toContain('pas « aucun blessé »')
    expect(text).toContain("Aucune écriture n'a été faite en base")
    expect(text).toContain('Écriture en base')
    expect(text).not.toContain('Statuts appliqués')
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
  })

  it("affiche le message d'erreur réel du serveur, pas un texte générique", async () => {
    const message = 'Aucun rapport de blessures trouvé en remontant 48 h depuis 2026-10-19T14:30-04:00'
    apiFetch.mockRejectedValue(new ApiError(message))
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(message)
    expect(wrapper.text()).not.toContain('Échec de la mise à jour')
  })
})

describe("InjuryUpdateCard -- retour d'attente (décision d'architecture n°35)", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  function respondAfter(ms, value) {
    apiFetch.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve(value), ms)))
  }
  const spinner = (wrapper) => wrapper.find('[data-testid="injury-spinner"]')

  it("ne montre jamais l'indicateur quand la réponse arrive en moins de 200 ms", async () => {
    respondAfter(10, REPORT)
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')
    for (const elapsed of [0, 5, 10, 100, 250, 600]) {
      await vi.advanceTimersByTimeAsync(elapsed === 0 ? 0 : 5)
      expect(spinner(wrapper).exists()).toBe(false)
    }
    await vi.advanceTimersByTimeAsync(1000)
    expect(spinner(wrapper).exists()).toBe(false)
    expect(wrapper.text()).toContain('Jock Landale')
  })

  it("affiche l'indicateur à partir de 200 ms et le garde au moins 300 ms, même si la réponse arrive juste après", async () => {
    respondAfter(210, REPORT)
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')

    await vi.advanceTimersByTimeAsync(199)
    expect(spinner(wrapper).exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(2) // t = 201 ms : affiché
    expect(spinner(wrapper).exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(10) // t = 211 ms : la réponse est arrivée, l'indicateur reste
    expect(spinner(wrapper).exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(280) // t = 491 ms : 291 ms d'affichage
    expect(spinner(wrapper).exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(20) // t = 511 ms : plus de 300 ms d'affichage
    expect(spinner(wrapper).exists()).toBe(false)
    expect(wrapper.text()).toContain('Jock Landale')
  })

  it("garde l'indicateur affiché jusqu'à la réponse quand elle est lente, et ne change jamais le libellé ni le nombre d'indicateurs", async () => {
    respondAfter(700, REPORT)
    const wrapper = mount(InjuryUpdateCard)
    expect(button(wrapper).text()).toBe(BUTTON_LABEL)
    await button(wrapper).trigger('click')

    for (const step of [100, 150, 200, 200]) {
      await vi.advanceTimersByTimeAsync(step)
      expect(button(wrapper).text()).toBe(BUTTON_LABEL)
      expect(wrapper.findAll('[data-testid="injury-spinner"]').length).toBeLessThanOrEqual(1)
    }
    // t = 650 ms : toujours en attente, indicateur affiché
    expect(spinner(wrapper).exists()).toBe(true)
    expect(button(wrapper).attributes('aria-busy')).toBe('true')
    await vi.advanceTimersByTimeAsync(100) // t = 750 ms : réponse reçue à 700 ms, > 300 ms d'affichage
    expect(spinner(wrapper).exists()).toBe(false)
    expect(button(wrapper).attributes('aria-busy')).toBe('false')
    expect(button(wrapper).text()).toBe(BUTTON_LABEL)
  })

  it('ignore un second clic pendant un traitement en cours', async () => {
    respondAfter(300, REPORT)
    const wrapper = mount(InjuryUpdateCard)
    await button(wrapper).trigger('click')
    await button(wrapper).trigger('click')
    expect(apiFetch).toHaveBeenCalledTimes(1)
  })
})
