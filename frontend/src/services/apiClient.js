const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Découple le client HTTP du store Pinia (évite un import circulaire, le
// store utilisant lui-même apiFetch pour l'appel de login). Configuré une
// fois au démarrage de l'app — voir main.js.
let tokenGetter = () => null

export function configureApiClient({ getToken }) {
  tokenGetter = getToken
}

export async function apiFetch(path, { method = 'GET', body, isFormData = false, headers = {} } = {}) {
  const finalHeaders = { ...headers }

  const token = tokenGetter()
  if (token) {
    finalHeaders['Authorization'] = `Bearer ${token}`
  }

  let finalBody = body
  if (body !== undefined && !isFormData) {
    finalHeaders['Content-Type'] = 'application/json'
    finalBody = JSON.stringify(body)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: finalBody,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      // Pas de corps JSON exploitable dans la réponse d'erreur.
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return null
  }
  return response.json()
}

// Pour les endpoints qui renvoient un fichier (ex: modèles CSV) plutôt que
// du JSON -- un lien <a href> classique ne porterait pas le header
// Authorization, ces routes étant protégées admin comme les autres.
export async function apiFetchBlob(path) {
  const finalHeaders = {}
  const token = tokenGetter()
  if (token) {
    finalHeaders['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { headers: finalHeaders })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      // Pas de corps JSON exploitable dans la réponse d'erreur.
    }
    throw new ApiError(response.status, detail)
  }

  return response.blob()
}
