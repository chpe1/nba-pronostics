import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, configureApiClient, ApiError } from './apiClient'

function mockFetchOnce({ ok, status, statusText = '', json }) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: vi.fn().mockResolvedValue(json ?? {}),
  })
}

describe('apiFetch', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    configureApiClient({ getToken: () => null })
  })

  it('adds the Authorization header when a token is present in the store', async () => {
    configureApiClient({ getToken: () => 'fake-jwt-token' })
    mockFetchOnce({ ok: true, status: 200, json: { hello: 'world' } })

    await apiFetch('/api/settings')

    const [, options] = global.fetch.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer fake-jwt-token')
  })

  it('omits the Authorization header when no token is present', async () => {
    configureApiClient({ getToken: () => null })
    mockFetchOnce({ ok: true, status: 200, json: {} })

    await apiFetch('/api/predictions/today')

    const [, options] = global.fetch.mock.calls[0]
    expect(options.headers.Authorization).toBeUndefined()
  })

  it('throws an ApiError with status 401 on an unauthorized response', async () => {
    mockFetchOnce({ ok: false, status: 401, statusText: 'Unauthorized', json: { detail: 'Token invalide' } })

    await expect(apiFetch('/api/imports/history')).rejects.toMatchObject({
      status: 401,
      message: 'Token invalide',
    })
    await expect(apiFetch('/api/imports/history')).rejects.toBeInstanceOf(ApiError)
  })

  it('throws an ApiError with status 500 on a server error response', async () => {
    mockFetchOnce({ ok: false, status: 500, statusText: 'Internal Server Error', json: {} })

    await expect(apiFetch('/api/auth/login')).rejects.toMatchObject({
      status: 500,
      message: 'Internal Server Error',
    })
  })

  it('sends a JSON body and Content-Type header for non-form requests', async () => {
    mockFetchOnce({ ok: true, status: 200, json: {} })

    await apiFetch('/api/auth/login', { method: 'POST', body: { username: 'admin', password: 'x' } })

    const [, options] = global.fetch.mock.calls[0]
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(options.body).toBe(JSON.stringify({ username: 'admin', password: 'x' }))
  })
})
