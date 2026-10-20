import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CsvUploadForm from './CsvUploadForm.vue'

// Écran d'import d'EFFECTIF (Décision d'architecture n°39, étape 5) : lignes à trancher, lignes en
// erreur, joueurs à détacher, compte-rendu. apiClient stubbé : aucun vrai réseau.
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'

const ROW_HOLLAND = {
  name: 'Ronald Holland II',
  team_abbreviation: 'DET',
  closest_absent_player: 'Ron Holland',
  distance: 3,
}
const ROW_NEW = { name: 'New Guy', team_abbreviation: 'BOS', closest_absent_player: null, distance: null }

const CANDIDATES = [
  { id: 11, name: 'Gone Veteran', team_abbreviation: 'BOS' },
  { id: 12, name: 'Ron Holland', team_abbreviation: 'DET' },
  { id: 13, name: 'Other Absent', team_abbreviation: 'LAL' },
  { id: 14, name: 'Free Agent F', team_abbreviation: null },
]

const DETACHABLE = [
  { id: 11, name: 'Gone Veteran', team_abbreviation: 'BOS', draft_pick: null, per_n1: 11.5, mpg_n1: 22.0 },
  { id: 12, name: 'Ron Holland', team_abbreviation: 'DET', draft_pick: null, per_n1: 11.7, mpg_n1: 19.9 },
  { id: 13, name: 'Other Absent', team_abbreviation: 'LAL', draft_pick: 40, per_n1: null, mpg_n1: null },
]

function rosterPreview(overrides = {}) {
  return {
    import_type: 'roster',
    filename: 'roster.csv',
    row_count: 10,
    error_count: 0,
    errors: [],
    matched_count: 8,
    unmatched: [],
    orphans: ['Gone Veteran', 'Ron Holland', 'Other Absent'],
    moved: [],
    no_prior_data: [],
    detachable: DETACHABLE,
    file_rows_without_match_count: 2,
    file_rows_without_match: [ROW_HOLLAND, ROW_NEW],
    association_candidates: CANDIDATES,
    row_errors: [],
    detachment_blocked: false,
    detachment_blocked_reason: null,
    // Règle du serveur : verdicts obligatoires quand une ligne sans correspondance ET un joueur absent coexistent.
    verdicts_required: true,
    ...overrides,
  }
}

let confirmResult = null

function stubApi(preview) {
  apiFetch.mockImplementation((path, options) => {
    if (path === '/api/teams') return Promise.resolve([])
    if (path === '/api/settings') return Promise.resolve({ current_season: '2026-2027', previous_season: '2025-2026' })
    if (path.startsWith('/api/imports/stats')) {
      // Une copie à chaque appel, comme le ferait une vraie réponse réseau (un objet identique ne
      // déclencherait pas le watch qui réinitialise verdicts et cases).
      if (path.includes('dry_run=true')) return Promise.resolve(structuredClone(preview))
      return Promise.resolve(confirmResult)
    }
    throw new Error(`chemin inattendu : ${path} ${options?.method}`)
  })
}

async function mountWithPreview(preview = rosterPreview()) {
  stubApi(preview)
  const wrapper = mount(CsvUploadForm)
  await flushPromises()
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'roster.csv')], configurable: true })
  await input.trigger('change')
  await wrapper.find('button').trigger('click') // « Aperçu »
  await flushPromises()
  return wrapper
}

const rowCards = (w) => w.findAll('[data-testid="row-to-decide"]')
const checkboxes = (w) => w.findAll('input[type="checkbox"]')
const confirmButton = (w) => w.get('[data-testid="confirm-button"]')

async function resolveBoth(wrapper) {
  const cards = rowCards(wrapper)
  await cards[0].find('input[value="same_player"]').setValue(true)
  await cards[0].find('select').setValue('12') // Ronald Holland II -> Ron Holland
  await cards[1].find('input[value="recruit"]').setValue(true)
}

beforeEach(() => {
  apiFetch.mockReset()
  confirmResult = {
    import_history: { import_type: 'roster', row_count: 10 },
    resolved_rows_count: 2,
    recruit_count: 1,
    recruit_names: ['New Guy'],
    association_count: 1,
    associations: [{ file_name: 'Ronald Holland II', player_id: 12, player_name: 'Ron Holland' }],
    detached_count: 2,
    detached_names: ['Gone Veteran', 'Other Absent'],
  }
})

describe("aperçu d'un effectif : trois sections, dans l'ordre des décisions", () => {
  it('affiche les lignes à trancher, puis les joueurs à détacher, ouvertes (sans dépliage)', async () => {
    const wrapper = await mountWithPreview()
    const html = wrapper.html()
    expect(wrapper.find('[data-testid="section-rows"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-detach"]').exists()).toBe(true)
    expect(html.indexOf('section-rows')).toBeLessThan(html.indexOf('section-detach'))
    // visibles sans dépliage : ni dans un <details>, et leurs noms sont dans le DOM
    expect(wrapper.find('details [data-testid="section-rows"]').exists()).toBe(false)
    expect(wrapper.find('details [data-testid="section-detach"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Ronald Holland II')
    expect(wrapper.text()).toContain('Gone Veteran')
  })

  it('affiche la section des lignes en erreur EN PREMIER (avant les lignes à trancher), avec numéro, contenu et message', async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({
        row_errors: [{ row: 3, player_name: 'Mystery Man', team: 'XXX', message: "Équipe inconnue : 'XXX'" }],
        error_count: 1,
        errors: [{ row: 3, message: "Équipe inconnue : 'XXX'" }],
      }),
    )
    const html = wrapper.html()
    // Une erreur se répare dans le fichier et oblige à refaire l'aperçu (verdicts remis à zéro) :
    // les erreurs viennent donc avant les lignes à trancher, puis les joueurs à détacher.
    expect(html.indexOf('section-errors')).toBeLessThan(html.indexOf('section-rows'))
    expect(html.indexOf('section-rows')).toBeLessThan(html.indexOf('section-detach'))
    const text = wrapper.get('[data-testid="section-errors"]').text()
    expect(text).toContain('Ligne 3')
    expect(text).toContain('Mystery Man')
    expect(text).toContain('XXX')
    expect(text).toContain("Équipe inconnue : 'XXX'")
    expect(text).toContain('Tout détachement est bloqué')
  })

  it("n'affiche pas la section des erreurs sans erreur", async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.find('[data-testid="section-errors"]').exists()).toBe(false)
  })

  it('groupe les joueurs à détacher par équipe, avec PER/MPG N-1 et rang de draft', async () => {
    const wrapper = await mountWithPreview()
    const groups = wrapper.findAll('[data-testid="detach-group"]')
    expect(groups.map((g) => g.get('h4').text())).toEqual(['BOS — 1 joueur(s)', 'DET — 1 joueur(s)', 'LAL — 1 joueur(s)'])
    expect(groups[0].text()).toContain('PER N-1 11.5')
    expect(groups[0].text()).toContain('MPG N-1 22.0')
    expect(groups[2].text()).toContain('pas de ligne N-1')
    expect(groups[2].text()).toContain('pick 40')
  })

  it('dit explicitement quand il ne reste aucune ligne à trancher', async () => {
    const wrapper = await mountWithPreview(rosterPreview({ file_rows_without_match: [], file_rows_without_match_count: 0 }))
    expect(wrapper.get('[data-testid="rows-none"]').text()).toContain('réellement parti')
  })
})

describe('aucun choix par défaut', () => {
  it('aucun bouton radio, aucun sélecteur, aucune case cochée au départ', async () => {
    const wrapper = await mountWithPreview()
    for (const card of rowCards(wrapper)) {
      for (const input of card.findAll('input[type="radio"]')) {
        expect(input.element.checked).toBe(false)
      }
    }
    for (const select of wrapper.findAll('select').filter((s) => s.attributes('aria-label')?.startsWith('Joueur'))) {
      expect(select.element.value).toBe('')
    }
    for (const box of checkboxes(wrapper)) expect(box.element.checked).toBe(false)
  })

  it("la suggestion est mise en évidence dans le sélecteur mais n'est jamais présélectionnée", async () => {
    const wrapper = await mountWithPreview()
    const card = rowCards(wrapper)[0]
    expect(card.text()).toContain('★ Ron Holland (DET)')
    expect(card.get('optgroup').attributes('label')).toContain('Suggestion')
    await card.find('input[value="same_player"]').setValue(true) // même en choisissant « même joueur »…
    expect(card.get('select').element.value).toBe('') // … la suggestion n'est pas sélectionnée
  })

  it('le bouton de confirmation dit simplement « Confirmer l\'import » quand rien n\'est coché', async () => {
    const wrapper = await mountWithPreview()
    expect(confirmButton(wrapper).text()).toBe("Confirmer l'import")
  })
})

describe('garde-fou : tant qu\'une ligne n\'a pas de verdict, le détachement est impossible', () => {
  it('annonce combien de lignes restent sans verdict, et pourquoi le détachement est impossible', async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toContain('2 ligne(s) sur 2 restent sans verdict')
    expect(wrapper.get('[data-testid="rows-block-notice"]').text()).toContain('La confirmation et le détachement sont impossibles')
    expect(wrapper.get('[data-testid="detach-block-notice"]').text()).toContain('2 ligne(s) du fichier sans correspondance')
  })

  it('« tout cocher » et les cases sont désactivés, avec l\'explication visible', async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
    for (const box of checkboxes(wrapper)) expect(box.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="detach-block-notice"]').isVisible()).toBe(true)
  })

  it("« même joueur que… » sans joueur choisi ne vaut pas verdict", async () => {
    const wrapper = await mountWithPreview()
    await rowCards(wrapper)[0].find('input[value="same_player"]').setValue(true)
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toContain('2 ligne(s) sur 2')
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
  })

  it('une seule ligne tranchée sur deux ne suffit pas', async () => {
    const wrapper = await mountWithPreview()
    await rowCards(wrapper)[1].find('input[value="recruit"]').setValue(true)
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toContain('1 ligne(s) sur 2')
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
  })

  it('« tout cocher » s\'ouvre quand toutes les lignes ont un verdict', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper)
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toContain('Les 2 ligne(s) ont un verdict')
    expect(wrapper.find('[data-testid="detach-block-notice"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeUndefined()
  })

  it('une ligne en erreur bloque le détachement même quand toutes les lignes sont tranchées', async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ row_errors: [{ row: 3, player_name: 'Mystery', team: 'XXX', message: 'Équipe inconnue' }] }),
    )
    await resolveBoth(wrapper)
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="detach-block-notice"]').text()).toContain('en erreur')
  })

  it('refuse de cocher quand le détachement est bloqué, même en forçant le geste', async () => {
    const wrapper = await mountWithPreview()
    await wrapper.get('[data-testid="check-all"]').trigger('click')
    expect(checkboxes(wrapper).filter((b) => b.element.checked)).toHaveLength(0)
  })
})

describe('détachement : cases, compte annoncé, envoi', () => {
  it('« tout cocher » coche tous les joueurs affichés et le bouton annonce le nombre', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper) // Ron Holland est associé : il n'est plus détachable
    await wrapper.get('[data-testid="check-all"]').trigger('click')
    expect(wrapper.get('[data-testid="checked-counter"]').text()).toBe('2 coché(s) sur 2')
    expect(confirmButton(wrapper).text()).toBe('Confirmer et détacher 2 joueurs')
  })

  it('un joueur associé à une ligne disparaît de la liste des détachables', async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.get('[data-testid="section-detach"]').text()).toContain('Ron Holland')
    await resolveBoth(wrapper)
    expect(wrapper.get('[data-testid="section-detach"]').text()).not.toContain('Ron Holland')
    expect(wrapper.get('[data-testid="section-detach"]').text()).toContain('Joueurs à détacher (2)')
  })

  it("une ligne qui redevient sans verdict vide les cases cochées : le détachement redevient impossible", async () => {
    const wrapper = await mountWithPreview()
    const cards = rowCards(wrapper)
    await cards[0].find('input[value="recruit"]').setValue(true)
    await cards[1].find('input[value="recruit"]').setValue(true)
    await wrapper.get('[data-testid="check-all"]').trigger('click')
    expect(confirmButton(wrapper).text()).toBe('Confirmer et détacher 3 joueurs')
    // la première ligne passe à « même joueur que… » sans joueur choisi : plus de verdict
    await cards[0].find('input[value="same_player"]').setValue(true)
    expect(confirmButton(wrapper).text()).toBe("Confirmer l'import")
    expect(wrapper.get('[data-testid="checked-counter"]').text()).toBe('0 coché(s) sur 3')
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
  })

  it("un joueur coché qui devient la cible d'une association est retiré de la sélection", async () => {
    const wrapper = await mountWithPreview()
    const cards = rowCards(wrapper)
    await cards[0].find('input[value="same_player"]').setValue(true)
    await cards[0].find('select').setValue('11') // Ronald Holland II -> Gone Veteran (provisoire)
    await cards[1].find('input[value="recruit"]').setValue(true)
    await wrapper.get('[data-testid="check-all"]').trigger('click') // 2 joueurs (Ron Holland, Other Absent)
    expect(confirmButton(wrapper).text()).toBe('Confirmer et détacher 2 joueurs')
    await cards[0].find('select').setValue('12') // la ligne désigne maintenant Ron Holland, coché
    expect(confirmButton(wrapper).text()).toBe('Confirmer et détacher 1 joueur') // Ron Holland retiré ; Gone Veteran revient à la liste, non coché
    expect(wrapper.get('[data-testid="section-detach"]').text()).not.toContain('Ron Holland')
    expect(wrapper.get('[data-testid="checked-counter"]').text()).toBe('1 coché(s) sur 2')
  })

  it('le singulier est employé pour un seul joueur', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper)
    await checkboxes(wrapper)[0].setValue(true)
    expect(confirmButton(wrapper).text()).toBe('Confirmer et détacher 1 joueur')
  })

  it('un joueur déjà choisi pour une autre ligne est désactivé dans les autres sélecteurs', async () => {
    const wrapper = await mountWithPreview()
    const cards = rowCards(wrapper)
    await cards[0].find('input[value="same_player"]').setValue(true)
    await cards[0].find('select').setValue('12')
    await cards[1].find('input[value="same_player"]').setValue(true)
    const option = cards[1].findAll('option').find((o) => o.element.value === '12')
    expect(option.attributes('disabled')).toBeDefined()
  })

  it('envoie à la confirmation les verdicts (JSON) et la liste explicite des identifiants à détacher', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper)
    await checkboxes(wrapper)[0].setValue(true) // Gone Veteran (11)
    await checkboxes(wrapper)[1].setValue(true) // Other Absent (13)
    await confirmButton(wrapper).trigger('click')
    await flushPromises()

    const call = apiFetch.mock.calls.find(([path]) => path.includes('dry_run=false'))
    expect(call).toBeTruthy()
    const [path, options] = call
    const params = new URLSearchParams(path.split('?')[1])
    expect(params.getAll('detach_player_ids')).toEqual(['11', '13'])
    expect(JSON.parse(options.body.get('verdicts'))).toEqual([
      { file_name: 'Ronald Holland II', verdict: 'same_player', player_id: 12 },
      { file_name: 'New Guy', verdict: 'recruit' },
    ])
  })

  it("n'envoie ni verdict ni identifiant quand rien n'a été décidé (aucun joueur absent : import permis sans verdict)", async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ verdicts_required: false, association_candidates: [], detachable: [], orphans: [] }),
    )
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    const [path, options] = apiFetch.mock.calls.find(([p]) => p.includes('dry_run=false'))
    expect(new URLSearchParams(path.split('?')[1]).getAll('detach_player_ids')).toEqual([])
    expect(options.body.get('verdicts')).toBeNull()
  })

  it("prévient que les lignes sans verdict seront importées comme recrues, SEULEMENT quand c'est permis (aucun joueur absent)", async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ verdicts_required: false, association_candidates: [], detachable: [], orphans: [] }),
    )
    expect(wrapper.get('[data-testid="unresolved-import-warning"]').text()).toContain(
      '2 ligne(s) sans verdict seront importées comme des recrues',
    )
    expect(wrapper.find('[data-testid="confirm-blocked-notice"]').exists()).toBe(false)
  })

  it("n'affiche pas « importées comme recrues » quand les verdicts sont obligatoires : l'avertissement serait faux", async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.find('[data-testid="unresolved-import-warning"]').exists()).toBe(false)
    await resolveBoth(wrapper)
    expect(wrapper.find('[data-testid="unresolved-import-warning"]').exists()).toBe(false)
  })

  it('un nouvel aperçu repart de zéro : aucun verdict, aucune case', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper)
    await checkboxes(wrapper)[0].setValue(true)
    await wrapper.find('button').trigger('click') // nouvel « Aperçu »
    await flushPromises()
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toContain('2 ligne(s) sur 2 restent sans verdict')
    expect(checkboxes(wrapper).filter((b) => b.element.checked)).toHaveLength(0)
  })
})

describe('confirmation : verdicts obligatoires quand une ligne sans correspondance ET un joueur absent coexistent', () => {
  it('le bouton de confirmation est désactivé, avec l\'explication visible à côté', async () => {
    const wrapper = await mountWithPreview()
    expect(confirmButton(wrapper).attributes('disabled')).toBeDefined()
    const notice = wrapper.get('[data-testid="confirm-blocked-notice"]')
    expect(notice.isVisible()).toBe(true)
    expect(notice.text()).toContain('Confirmation impossible')
    expect(notice.text()).toContain('2 ligne(s) du fichier sans correspondance')
    expect(notice.text()).toContain('4 joueur(s) de la base sont absents du fichier')
  })

  it("un clic sur le bouton désactivé n'envoie rien", async () => {
    const wrapper = await mountWithPreview()
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    expect(apiFetch.mock.calls.filter(([p]) => p.includes('dry_run=false'))).toHaveLength(0)
  })

  it("reste désactivé tant qu'une seule ligne est sans verdict, puis s'active quand toutes sont tranchées", async () => {
    const wrapper = await mountWithPreview()
    await rowCards(wrapper)[1].find('input[value="recruit"]').setValue(true)
    expect(confirmButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="confirm-blocked-notice"]').text()).toContain('1 ligne(s)')
    await resolveBoth(wrapper)
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="confirm-blocked-notice"]').exists()).toBe(false)
  })

  it("n'est PAS bloqué quand aucun joueur de la base n'est absent du fichier (une ligne sans correspondance ne peut être qu'une recrue)", async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ verdicts_required: false, association_candidates: [], detachable: [], orphans: [] }),
    )
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="confirm-blocked-notice"]').exists()).toBe(false)
    // la section dit que le verdict est facultatif, et ne parle plus de confirmation impossible
    expect(wrapper.get('[data-testid="rows-optional-note"]').text()).toContain('Le verdict est facultatif')
    expect(wrapper.find('[data-testid="rows-block-notice"]').exists()).toBe(false)
    // le compteur annonce la conséquence, pas un manque alarmiste
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toBe(
      '2 ligne(s) sans verdict — elles seront importées comme recrues.',
    )
  })

  it('garde la formulation « restent sans verdict » quand les verdicts sont obligatoires', async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.get('[data-testid="rows-counter"]').text()).toBe('2 ligne(s) sur 2 restent sans verdict.')
  })

  it("n'est PAS bloqué quand toutes les lignes ont une correspondance", async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ verdicts_required: false, file_rows_without_match: [], file_rows_without_match_count: 0 }),
    )
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('« Tout décocher » est grisé dans les mêmes conditions que « Tout cocher »', async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="uncheck-all"]').attributes('disabled')).toBeDefined()
    await resolveBoth(wrapper)
    expect(wrapper.get('[data-testid="check-all"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="uncheck-all"]').attributes('disabled')).toBeUndefined()
  })

  it('« Tout décocher » est aussi grisé par une ligne en erreur, même quand toutes les lignes sont tranchées', async () => {
    const wrapper = await mountWithPreview(
      rosterPreview({ row_errors: [{ row: 3, player_name: 'Mystery', team: 'XXX', message: 'Équipe inconnue' }] }),
    )
    await resolveBoth(wrapper)
    expect(wrapper.get('[data-testid="uncheck-all"]').attributes('disabled')).toBeDefined()
  })
})

describe("compte-rendu après l'import", () => {
  it('affiche les lignes tranchées, recrues, associations et joueurs détachés, avec leurs noms', async () => {
    const wrapper = await mountWithPreview()
    await resolveBoth(wrapper)
    await wrapper.get('[data-testid="check-all"]').trigger('click')
    await confirmButton(wrapper).trigger('click')
    await flushPromises()

    const report = wrapper.get('[data-testid="import-report"]').text()
    expect(report).toContain('2 ligne(s) tranchée(s)')
    expect(report).toContain('1 recrue(s)')
    expect(report).toContain('1 association(s)')
    expect(report).toContain('Recrues : New Guy')
    expect(report).toContain('« Ronald Holland II » rattachée à Ron Holland (nom en base inchangé)')
    expect(report).toContain('2 joueur(s) détaché(s)')
    expect(report).toContain('Gone Veteran')
    expect(report).toContain('Other Absent')
    expect(wrapper.find('[data-testid="section-rows"]').exists()).toBe(false) // l'aperçu est refermé
  })
})

describe("attente (décision d'architecture n°35)", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  async function mountForTiming() {
    stubApi(rosterPreview({ file_rows_without_match: [], file_rows_without_match_count: 0 }))
    const wrapper = mount(CsvUploadForm)
    await flushPromises()
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'roster.csv')], configurable: true })
    await input.trigger('change')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    return wrapper
  }
  const spinner = (w) => w.find('[data-testid="import-spinner"]')

  function respondConfirmAfter(ms) {
    apiFetch.mockImplementation((path) => {
      if (path.includes('dry_run=false')) return new Promise((resolve) => setTimeout(() => resolve(confirmResult), ms))
      if (path === '/api/teams') return Promise.resolve([])
      if (path === '/api/settings') return Promise.resolve({ current_season: '2026-2027', previous_season: '2025-2026' })
      return Promise.resolve(rosterPreview({ file_rows_without_match: [], file_rows_without_match_count: 0 }))
    })
  }

  it("ne montre jamais l'indicateur pour une réponse rapide, et le libellé ne change pas", async () => {
    const wrapper = await mountForTiming()
    respondConfirmAfter(10)
    const label = confirmButton(wrapper).text()
    await confirmButton(wrapper).trigger('click')
    for (const _ of [1, 2, 3, 4]) {
      await vi.advanceTimersByTimeAsync(50)
      expect(spinner(wrapper).exists()).toBe(false)
    }
    expect(label).toBe("Confirmer l'import")
  })

  it("affiche l'indicateur après 200 ms et le garde au moins 300 ms, libellé inchangé", async () => {
    const wrapper = await mountForTiming()
    respondConfirmAfter(210)
    await confirmButton(wrapper).trigger('click')
    await vi.advanceTimersByTimeAsync(199)
    expect(spinner(wrapper).exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(2) // 201 ms
    expect(spinner(wrapper).exists()).toBe(true)
    expect(confirmButton(wrapper).text()).toBe("Confirmer l'import")
    await vi.advanceTimersByTimeAsync(10) // réponse reçue à 210 ms : l'indicateur reste
    expect(spinner(wrapper).exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(280) // 291 ms d'affichage
    expect(spinner(wrapper).exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(20) // > 300 ms
    expect(spinner(wrapper).exists()).toBe(false)
  })

  it('ignore un second clic pendant le traitement', async () => {
    const wrapper = await mountForTiming()
    respondConfirmAfter(300)
    await confirmButton(wrapper).trigger('click')
    await confirmButton(wrapper).trigger('click')
    expect(apiFetch.mock.calls.filter(([p]) => p.includes('dry_run=false'))).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1000)
  })
})
