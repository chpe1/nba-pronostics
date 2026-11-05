import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import OddsFetchCard from './OddsFetchCard.vue'

vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch, ApiError } from '@/services/apiClient'

const REPORT = {
  matched: [
    { game_id: 1, label: 'PHI@DET', rows: 38, bookmakers: 19, missing_screen_bookmakers: [] },
    { game_id: 2, label: 'OKC@SAS', rows: 4, bookmakers: 2, missing_screen_bookmakers: ['unibet_fr'] },
  ],
  unmatched: [
    { home_team: 'Nowhere Hawks', away_team: 'Boston Celtics', reason: 'unknown_team', unknown_labels: ['Nowhere Hawks'] },
  ],
  ignored: [{ game_id: 3, label: 'LAL@MIA', reason: 'started' }],
  no_odds_yet: [{ game_id: 4, label: 'NYK@CHI', reason: 'not_in_response' }],
  time_gaps: [
    { game_id: 1, label: 'PHI@DET', gap_minutes: -30, alert: true },
    { game_id: 2, label: 'OKC@SAS', gap_minutes: 5, alert: false },
  ],
  anomalies: [{ game_id: 1, label: 'PHI@DET', bookmaker: 'betfair_ex_eu', reason: 'bad_price' }],
  rows_written: 42,
}

const RUN = {
  id: 7,
  fetched_at: '2026-11-04T21:00:00Z',
  trigger: 'button',
  http_status: 200,
  error: null,
  credits_used: 1,
  credits_remaining: 479,
  events_returned: 5,
  rows_written: 42,
  matched_count: 2,
  unmatched_count: 1,
  no_odds_yet_count: 1,
  ignored_count: 1,
  time_gap_count: 1,
  anomaly_count: 1,
  report: REPORT,
}

const STATUS = () => ({
  scheduler_enabled: true,
  api_key_configured: true,
  credits_threshold: 20,
  last_known_credits: 480,
  last_known_credits_at: '2026-11-04T20:00:00Z',
  scheduled_suspended: false,
  latest_run: null,
  recent_runs: [],
  alerts: [],
})

beforeEach(() => {
  apiFetch.mockReset()
})

describe('OddsFetchCard', () => {
  it('le bouton lance UN appel et affiche le compte-rendu complet, chaque rubrique séparée', async () => {
    apiFetch.mockResolvedValue(RUN)
    const wrapper = mount(OddsFetchCard, { props: { status: STATUS() } })
    await wrapper.find('[data-testid="odds-fetch-button"]').trigger('click')
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledWith('/api/odds/fetch', { method: 'POST' })
    expect(wrapper.find('[data-testid="odds-report-counts"]').text()).toContain('42 cote(s) écrite(s)')
    const unmatched = wrapper.find('[data-testid="odds-report-unmatched"]').text()
    expect(unmatched).toContain('rien n\'a été deviné')
    expect(unmatched).toContain('Nowhere Hawks')
    // « marché pas encore ouvert » n'est JAMAIS rangé parmi les non reconnus
    expect(unmatched).not.toContain('NYK@CHI')
    expect(wrapper.find('[data-testid="odds-report-no-odds"]').text()).toContain('NYK@CHI')
    expect(wrapper.find('[data-testid="odds-report-no-odds"]').text()).toContain('marché pas encore ouvert')
    expect(wrapper.find('[data-testid="odds-report-time-gaps"]').text()).toContain('PHI@DET : 30 min plus tôt')
    expect(wrapper.find('[data-testid="odds-report-time-gaps"]').text()).not.toContain('OKC@SAS')
    expect(wrapper.find('[data-testid="odds-report-ignored"]').text()).toContain('coup d\'envoi passé')
    expect(wrapper.find('[data-testid="odds-report-anomalies"]').text()).toContain('betfair_ex_eu')
    expect(wrapper.find('[data-testid="odds-report-matched"]').text()).toContain('manque unibet_fr')
    expect(wrapper.emitted('fetched')).toHaveLength(1)
  })

  it('un double clic ne coûte pas deux crédits : un seul appel tant que le premier n\'a pas répondu', async () => {
    let resolve
    apiFetch.mockImplementation(() => new Promise((r) => (resolve = r)))
    const wrapper = mount(OddsFetchCard, { props: { status: STATUS() } })
    const button = wrapper.find('[data-testid="odds-fetch-button"]')
    await button.trigger('click')
    await button.trigger('click')
    await button.trigger('click')
    expect(apiFetch).toHaveBeenCalledTimes(1)
    resolve(RUN)
    await flushPromises()
    await button.trigger('click') // une fois la réponse reçue, un nouveau relevé redevient possible
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  describe("attente (Décision n°35) : 200 ms avant l'indicateur, 300 ms minimum une fois affiché, libellé intact", () => {
    let resolveCall
    const spinner = (w) => w.find('[data-testid="odds-fetch-spinner"]')
    const label = (w) => w.find('[data-testid="odds-fetch-button"]').text()

    async function start() {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
      apiFetch.mockImplementation(() => new Promise((resolve) => (resolveCall = resolve)))
      const wrapper = mount(OddsFetchCard, { props: { status: STATUS() } })
      await wrapper.find('[data-testid="odds-fetch-button"]').trigger('click')
      return wrapper
    }
    async function advance(ms) {
      await vi.advanceTimersByTimeAsync(ms)
      await nextTick()
    }
    afterEach(() => {
      vi.useRealTimers()
    })

    it('aucun indicateur à 199 ms, indicateur à 200 ms', async () => {
      const wrapper = await start()
      await advance(199)
      expect(spinner(wrapper).exists()).toBe(false)
      await advance(1)
      expect(spinner(wrapper).exists()).toBe(true)
      expect(wrapper.find('[data-testid="odds-fetch-button"]').attributes('aria-busy')).toBe('true')
    })

    it("réponse en moins de 200 ms : l'indicateur n'apparaît jamais", async () => {
      const wrapper = await start()
      await advance(50)
      resolveCall(RUN)
      await advance(0)
      await advance(500)
      expect(spinner(wrapper).exists()).toBe(false)
      expect(wrapper.emitted('fetched')).toHaveLength(1)
    })

    it('affiché à 200 ms, il reste au moins 300 ms même si la réponse arrive aussitôt après', async () => {
      const wrapper = await start()
      await advance(200)
      expect(spinner(wrapper).exists()).toBe(true)
      resolveCall(RUN) // réponse à 200 ms : l'indicateur doit tenir jusqu'à 500 ms
      await advance(299)
      expect(spinner(wrapper).exists()).toBe(true)
      await advance(2)
      expect(spinner(wrapper).exists()).toBe(false)
      expect(wrapper.emitted('fetched')).toHaveLength(1)
    })

    it('le libellé du bouton reste « Relever les cotes maintenant » à chaque instant, indicateur affiché compris', async () => {
      const wrapper = await start()
      expect(label(wrapper)).toBe('Relever les cotes maintenant')
      await advance(250)
      expect(spinner(wrapper).exists()).toBe(true)
      expect(label(wrapper)).toBe('Relever les cotes maintenant')
      resolveCall(RUN)
      await advance(400)
      expect(label(wrapper)).toBe('Relever les cotes maintenant')
    })
  })

  it('un échec affiche le message de l\'API tel quel et recharge quand même (l\'appel est journalisé)', async () => {
    apiFetch.mockImplementation(() => Promise.reject(new ApiError('the-odds-api a répondu 429 : quota')))
    const wrapper = mount(OddsFetchCard, { props: { status: STATUS() } })
    await wrapper.find('[data-testid="odds-fetch-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="odds-fetch-error"]').text()).toBe('the-odds-api a répondu 429 : quota')
    expect(wrapper.find('[data-testid="odds-fetch-report"]').exists()).toBe(false)
    expect(wrapper.emitted('fetched')).toHaveLength(1)
  })

  it('affiche les crédits restants et dit quand le relevé horaire est suspendu (sans dire « reprise manuelle »)', () => {
    const suspended = { ...STATUS(), last_known_credits: 12, scheduled_suspended: true }
    const wrapper = mount(OddsFetchCard, { props: { status: suspended } })
    expect(wrapper.find('[data-testid="odds-credits"]').text()).toBe('12')
    const text = wrapper.find('[data-testid="odds-task-state"]').text()
    expect(text).toContain('SUSPENDU')
    expect(text).toContain('reprendra seul')
  })

  it('dit si la tâche est désactivée ou si la clé manque', () => {
    const off = mount(OddsFetchCard, { props: { status: { ...STATUS(), scheduler_enabled: false } } })
    expect(off.find('[data-testid="odds-task-state"]').text()).toContain('désactivé')
    const nokey = mount(OddsFetchCard, { props: { status: { ...STATUS(), api_key_configured: false } } })
    expect(nokey.find('[data-testid="odds-task-state"]').text()).toContain("clé de l'API n'est pas configurée")
  })

  it('le journal distingue un relevé, une relecture gratuite du solde et un échec', () => {
    const status = {
      ...STATUS(),
      recent_runs: [
        { ...RUN, id: 3, report: null },
        { ...RUN, id: 2, trigger: 'scheduled', events_returned: 0, credits_used: 0, rows_written: 0, report: null },
        { ...RUN, id: 1, http_status: 500, error: 'the-odds-api a répondu 500', credits_used: null, report: null },
      ],
    }
    const wrapper = mount(OddsFetchCard, { props: { status } })
    expect(wrapper.find('[data-testid="odds-run-3"]').text()).toContain('42 cote(s) écrite(s)')
    expect(wrapper.find('[data-testid="odds-run-2"]').text()).toContain('relecture gratuite du solde')
    expect(wrapper.find('[data-testid="odds-run-1"]').text()).toContain('ÉCHEC (HTTP 500)')
  })

  it("au chargement, montre le dernier compte-rendu connu du serveur, sauf pour une simple relecture du solde", () => {
    const withReport = mount(OddsFetchCard, { props: { status: { ...STATUS(), latest_run: RUN } } })
    expect(withReport.find('[data-testid="odds-fetch-report"]').exists()).toBe(true)
    const balanceOnly = {
      ...RUN, events_returned: 0, credits_used: 0, rows_written: 0, report: { balance_check_only: true },
    }
    const wrapper = mount(OddsFetchCard, { props: { status: { ...STATUS(), latest_run: balanceOnly } } })
    expect(wrapper.find('[data-testid="odds-fetch-report"]').exists()).toBe(false)
  })
})
