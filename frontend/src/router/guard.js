// Logique pure, isolée de vue-router/Pinia pour rester testable sans DOM
// (voir router-guard.test.js). Retourne `true` pour laisser passer la
// navigation, ou une cible de redirection (objet accepté par vue-router) sinon.
export function requiresAuthGuard(to, isAuthenticated) {
  if (to.meta?.requiresAuth && !isAuthenticated) {
    return { name: 'login' }
  }
  return true
}
