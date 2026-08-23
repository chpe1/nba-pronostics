import { describe, it, expect } from 'vitest'
import { requiresAuthGuard } from './guard'

describe('requiresAuthGuard', () => {
  it('redirects /admin/* to /login when there is no token', () => {
    const to = { path: '/admin/imports', meta: { requiresAuth: true } }
    expect(requiresAuthGuard(to, false)).toEqual({ name: 'login' })
  })

  it('lets /admin/* through when authenticated', () => {
    const to = { path: '/admin/settings', meta: { requiresAuth: true } }
    expect(requiresAuthGuard(to, true)).toBe(true)
  })

  it('lets public routes through regardless of auth state', () => {
    const to = { path: '/', meta: {} }
    expect(requiresAuthGuard(to, false)).toBe(true)
    expect(requiresAuthGuard(to, true)).toBe(true)
  })
})
