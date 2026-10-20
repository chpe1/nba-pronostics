import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AdminPlayersView from './AdminPlayersView.vue'

// Étape 6 du chantier des agents libres (Décision d'architecture n°39) : l'écran Joueurs sait afficher,
// filtrer et REPLACER un agent libre -- jamais le détacher. apiClient stubbé : aucun vrai réseau.
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'

const TEAMS = [
  { id: 1, name: 'Boston Celtics', abbreviation: 'BOS' },
  { id: 2, name: 'Detroit Pistons', abbreviation: 'DET' },
]
const base = { draft_pick: null, per: 12.5, mpg: 22, injury_status: 'healthy', is_active: true }
const TATUM = { ...base, id: 1, name: 'Jayson Tatum', team_id: 1, team_name: 'Boston Celtics', team_abbreviation: 'BOS' }
const HOLLAND = { ...base, id: 12, name: 'Ron Holland', team_id: null, team_name: null, team_abbreviation: null }
const GONE = { ...base, id: 13, name: 'Gone Veteran', team_id: null, team_name: null, team_abbreviation: null }

let patchCalls
let confirmSpy

function stubApi() {
  patchCalls = []
  apiFetch.mockImplementation((path, options = {}) => {
    if (path === '/api/teams') return Promise.resolve(TEAMS)
    if (options.method === 'PATCH') {
      const id = Number(path.split('/').pop())
      patchCalls.push({ id, body: options.body })
      const original = [TATUM, HOLLAND, GONE].find((p) => p.id === id)
      const team = TEAMS.find((t) => t.id === options.body.team_id)
      return Promise.resolve({
        ...original,
        ...options.body,
        team_id: team ? team.id : original.team_id,
        team_name: team ? team.name : original.team_name,
        team_abbreviation: team ? team.abbreviation : original.team_abbreviation,
      })
    }
    if (path === '/api/players?free_agent=true') return Promise.resolve([HOLLAND, GONE])
    if (path === '/api/players?team_id=1') return Promise.resolve([TATUM])
    if (path === '/api/players') return Promise.resolve([TATUM, HOLLAND, GONE])
    throw new Error(`chemin inattendu : ${path}`)
  })
}

async function mountView() {
  stubApi()
  const wrapper = mount(AdminPlayersView)
  await flushPromises()
  return wrapper
}

const filterSelect = (w) => w.get('#team-filter')
const cards = (w) => w.findAll('[data-testid="player-card"]')
const cardOf = (w, name) => cards(w).find((c) => c.find('input[type="text"]').element.value === name)
const teamSelectOf = (card) => card.findAll('select')[0]
const calls = (path) => apiFetch.mock.calls.filter(([p]) => p === path).length

async function chooseFilter(wrapper, value) {
  const select = filterSelect(wrapper)
  select.element.value = value
  await select.trigger('change')
  await flushPromises()
}

beforeEach(() => {
  apiFetch.mockReset()
  confirmSpy = vi.spyOn(window, 'confirm')
})
afterEach(() => confirmSpy.mockRestore())

describe('filtre « Agents libres »', () => {
  it('propose une entrée « Agents libres » à côté de « Toutes les équipes » et des équipes', async () => {
    const wrapper = await mountView()
    const labels = filterSelect(wrapper).findAll('option').map((o) => o.text())
    expect(labels).toEqual(['Toutes les équipes', 'Agents libres', 'Boston Celtics', 'Detroit Pistons'])
  })

  it('appelle le filtre dédié du serveur et n\'affiche que les agents libres', async () => {
    const wrapper = await mountView()
    await chooseFilter(wrapper, 'free-agent')
    expect(calls('/api/players?free_agent=true')).toBe(1)
    expect(cards(wrapper).map((c) => c.find('input[type="text"]').element.value)).toEqual(['Ron Holland', 'Gone Veteran'])
    expect(filterSelect(wrapper).element.value).toBe('free-agent')
  })

  it('le filtre par équipe fonctionne toujours (team_id)', async () => {
    const wrapper = await mountView()
    await chooseFilter(wrapper, '1')
    expect(calls('/api/players?team_id=1')).toBe(1)
    expect(cards(wrapper)).toHaveLength(1)
  })
})

describe('affichage d\'un agent libre', () => {
  it('écrit « agent libre » au lieu d\'une abréviation vide, sans « null »', async () => {
    const wrapper = await mountView()
    const holland = cardOf(wrapper, 'Ron Holland')
    expect(holland.text()).toContain('agent libre — healthy')
    expect(wrapper.text()).not.toContain('null')
    expect(cardOf(wrapper, 'Jayson Tatum').text()).toContain('BOS — healthy')
  })

  it('le sélecteur d\'équipe affiche l\'état courant « agent libre », que l\'on ne peut pas choisir', async () => {
    const wrapper = await mountView()
    const select = teamSelectOf(cardOf(wrapper, 'Ron Holland'))
    const current = select.findAll('option').find((o) => o.text() === '— Agent libre —')
    expect(current).toBeTruthy()
    expect(current.attributes('disabled')).toBeDefined() // jamais une valeur à choisir
    expect(select.element.value).toBe('') // et c'est lui qui est affiché
    // un joueur rattaché n'a pas cette option
    const tatum = teamSelectOf(cardOf(wrapper, 'Jayson Tatum'))
    expect(tatum.findAll('option').some((o) => o.text().includes('Agent libre'))).toBe(false)
  })

  it("l'option reste courte ; la consigne est dans un texte d'aide sous le champ, absent des joueurs rattachés", async () => {
    const wrapper = await mountView()
    const holland = cardOf(wrapper, 'Ron Holland')
    const option = teamSelectOf(holland).findAll('option').find((o) => o.text().includes('Agent libre'))
    expect(option.text().length).toBeLessThanOrEqual(20) // plus de phrase coupée en plein mot sur petit écran
    expect(holland.get('[data-testid="free-agent-help"]').text()).toContain('choisissez-en une pour replacer ce joueur')
    expect(cardOf(wrapper, 'Jayson Tatum').find('[data-testid="free-agent-help"]').exists()).toBe(false)
  })

  it('la confirmation de suppression dit « agent libre » et jamais « (null) »', async () => {
    const wrapper = await mountView()
    confirmSpy.mockReturnValue(false)
    const holland = cardOf(wrapper, 'Ron Holland')
    await holland.findAll('button').find((b) => b.text() === 'Supprimer').trigger('click')
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    const message = confirmSpy.mock.calls[0][0]
    expect(message).toContain('Ron Holland (agent libre)')
    expect(message).not.toContain('null')
  })
})

describe('enregistrement : jamais de team_id 0 ni null', () => {
  const save = (card) => card.findAll('button').find((b) => b.text() === 'Enregistrer').trigger('click')

  it('un agent libre dont on corrige un autre champ est enregistré SANS team_id', async () => {
    const wrapper = await mountView()
    const holland = cardOf(wrapper, 'Ron Holland')
    await holland.findAll('input[type="number"]')[1].setValue('15') // PER
    await save(holland)
    await flushPromises()
    expect(patchCalls).toHaveLength(1)
    expect(patchCalls[0].body).not.toHaveProperty('team_id') // ni 0, ni null, ni absent-converti
    expect(patchCalls[0].body.per).toBe(15)
  })

  it('replacer un agent libre envoie un team_id numérique, et la fiche quitte la liste des agents libres', async () => {
    const wrapper = await mountView()
    await chooseFilter(wrapper, 'free-agent')
    const holland = cardOf(wrapper, 'Ron Holland')
    await teamSelectOf(holland).setValue(2) // Detroit Pistons
    await save(holland)
    await flushPromises()
    expect(patchCalls[0].body.team_id).toBe(2)
    expect(cards(wrapper).map((c) => c.find('input[type="text"]').element.value)).toEqual(['Gone Veteran'])
    expect(wrapper.text()).toContain('Ron Holland est maintenant à Detroit Pistons')
  })

  it('un joueur rattaché garde son team_id numérique à l\'enregistrement', async () => {
    const wrapper = await mountView()
    const tatum = cardOf(wrapper, 'Jayson Tatum')
    await save(tatum)
    await flushPromises()
    expect(patchCalls[0].body.team_id).toBe(1)
  })
})

describe('filtre d\'équipe : annulation d\'une modification non enregistrée (conflit v-model + @change, décision n°31)', () => {
  it('sans saisie en attente, changer de filtre ne demande aucune confirmation', async () => {
    const wrapper = await mountView()
    await chooseFilter(wrapper, '1')
    expect(confirmSpy).not.toHaveBeenCalled()
  })

  it('annulée : le sélecteur reste sur le filtre précédent et la liste n\'est pas rechargée', async () => {
    const wrapper = await mountView()
    const before = calls('/api/players?team_id=1')
    await cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1].setValue('99') // saisie non enregistrée
    confirmSpy.mockReturnValue(false)
    await chooseFilter(wrapper, '1')
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toContain('saisie non enregistrée')
    expect(filterSelect(wrapper).element.value).toBe('') // « Toutes les équipes » : l'option AFFICHÉE est revenue
    expect(calls('/api/players?team_id=1')).toBe(before) // pas de rechargement
    expect(cards(wrapper)).toHaveLength(3)
    expect(cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1].element.value).toBe('99') // la saisie survit
    // ... et l'état reste cohérent APRÈS un re-rendu sans rapport (le défaut du conflit v-model + @change :
    // la ref avait déjà pris la valeur annulée, l'option affichée y retombait au rendu suivant)
    await cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1].setValue('98')
    await flushPromises()
    expect(filterSelect(wrapper).element.value).toBe('')
  })

  it('confirmée : le filtre change et la liste est rechargée', async () => {
    const wrapper = await mountView()
    await cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1].setValue('99')
    confirmSpy.mockReturnValue(true)
    await chooseFilter(wrapper, 'free-agent')
    expect(filterSelect(wrapper).element.value).toBe('free-agent')
    expect(calls('/api/players?free_agent=true')).toBe(1)
  })

  it('annulée vers « Agents libres » : revient aussi à la valeur confirmée, qui peut être un autre filtre', async () => {
    const wrapper = await mountView()
    await chooseFilter(wrapper, '1') // confirmé : filtre équipe 1
    await cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1].setValue('99')
    confirmSpy.mockReturnValue(false)
    await chooseFilter(wrapper, 'free-agent')
    expect(filterSelect(wrapper).element.value).toBe('1')
  })

  it('un changement d\'équipe non enregistré (replacement d\'un agent libre) compte comme une saisie à ne pas perdre', async () => {
    const wrapper = await mountView()
    await teamSelectOf(cardOf(wrapper, 'Ron Holland')).setValue(2)
    confirmSpy.mockReturnValue(false)
    await chooseFilter(wrapper, '1')
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(filterSelect(wrapper).element.value).toBe('')
  })

  it('une saisie remise à sa valeur d\'origine n\'est pas une modification (pas de faux positif)', async () => {
    const wrapper = await mountView()
    const input = cardOf(wrapper, 'Jayson Tatum').findAll('input[type="number"]')[1]
    await input.setValue('99')
    await input.setValue('12.5')
    await chooseFilter(wrapper, '1')
    expect(confirmSpy).not.toHaveBeenCalled()
  })
})
