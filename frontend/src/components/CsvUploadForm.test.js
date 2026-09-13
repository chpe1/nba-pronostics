import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CsvUploadForm from './CsvUploadForm.vue'

// apiClient stubbé plutôt qu'appelé réellement (pas de vrai réseau/fetch en test de composant,
// même principe que les autres tests de ce projet) -- le comportement testé ici (réinitialisation
// de l'aperçu) ne dépend pas du vrai contenu des réponses, seulement de leur forme.
vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

import { apiFetch } from '@/services/apiClient'

const PREVIEW_RESPONSE = {
  import_type: 'players_advanced',
  filename: 'roster.csv',
  row_count: 12,
  error_count: 0,
  errors: [],
  sample_rows: [{ Player: 'Jayson Tatum' }],
  season_type: 'current',
  season: null,
  resolved_team_name: null,
  resolved_team_abbreviation: null,
}

function stubApiFetch() {
  apiFetch.mockImplementation((path) => {
    if (path === '/api/teams') {
      return Promise.resolve([{ id: 1, name: 'Boston Celtics' }])
    }
    if (path === '/api/settings') {
      return Promise.resolve({ current_season: '2026-2027', previous_season: '2025-2026' })
    }
    if (path.startsWith('/api/imports/stats')) {
      return Promise.resolve(PREVIEW_RESPONSE)
    }
    throw new Error(`chemin inattendu dans le test : ${path}`)
  })
}

// Le texte statique de l'encadré explicatif contient lui-même la phrase "Confirmer l'import"
// (nom du bouton cité dans l'instruction) -- chercher ce texte dans wrapper.text() donnerait donc
// un faux positif que l'aperçu soit affiché ou non. On cherche le VRAI bouton, par son texte exact.
function confirmButton(wrapper) {
  return wrapper.findAll('button').find((btn) => btn.text() === "Confirmer l'import")
}

function setFile(input, file) {
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
}

async function mountWithPreview() {
  const wrapper = mount(CsvUploadForm)
  await flushPromises() // laisse loadTeams()/loadCurrentSeason() (onMounted) se résoudre

  const file = new File(['contenu'], 'roster.csv', { type: 'text/csv' })
  const input = wrapper.find('input[type="file"]')
  setFile(input, file)
  await input.trigger('change')

  await wrapper.find('button').trigger('click') // "Aperçu" -- premier bouton
  await flushPromises()

  return wrapper
}

beforeEach(() => {
  apiFetch.mockReset()
  stubApiFetch()
})

describe("CsvUploadForm.vue -- réinitialisation de l'aperçu (point 2 du chantier import CSV)", () => {
  it("affiche l'aperçu et le bouton de confirmation après un Aperçu réussi", async () => {
    const wrapper = await mountWithPreview()
    expect(wrapper.text()).toContain('Type détecté')
    expect(confirmButton(wrapper)).toBeTruthy()
  })

  it("vide l'aperçu (et masque Confirmer l'import) quand la saison change après coup", async () => {
    const wrapper = await mountWithPreview()

    const previousRadio = wrapper.find('input[type="radio"][value="previous"]')
    await previousRadio.setValue(true)

    expect(wrapper.text()).not.toContain('Type détecté')
    expect(confirmButton(wrapper)).toBeFalsy()
  })

  it("vide l'aperçu quand l'équipe change après coup, même si la saison ne bouge pas", async () => {
    const wrapper = await mountWithPreview()

    await wrapper.find('select').setValue('1')

    expect(wrapper.text()).not.toContain('Type détecté')
    expect(confirmButton(wrapper)).toBeFalsy()
  })

  it("vide l'aperçu même si la saison revient à sa valeur d'origine (aucune exception faite au strict changement de valeur)", async () => {
    const wrapper = await mountWithPreview()

    const previousRadio = wrapper.find('input[type="radio"][value="previous"]')
    const currentRadio = wrapper.find('input[type="radio"][value="current"]')
    await previousRadio.setValue(true)
    await currentRadio.setValue(true) // retour à l'état de départ

    expect(confirmButton(wrapper)).toBeFalsy()
  })

  it("vide l'aperçu au changement de fichier (comportement préexistant, inchangé)", async () => {
    const wrapper = await mountWithPreview()

    const otherFile = new File(['autre'], 'autre.csv', { type: 'text/csv' })
    const input = wrapper.find('input[type="file"]')
    setFile(input, otherFile)
    await input.trigger('change')

    expect(confirmButton(wrapper)).toBeFalsy()
  })
})
