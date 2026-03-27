import { ref, readonly } from 'vue'
import { UserManager, type User, type UserManagerSettings } from 'oidc-client-ts'

const user = ref<User | null>(null)
// Stores the raw master token when the user authenticates via token (not OIDC).
// Initialized from sessionStorage so the token survives F5 within the same tab/session.
const masterToken = ref<string | null>(sessionStorage.getItem('master_token'))
const isAuthenticated = ref(false)
const isAuthLoading = ref(true)
const authEnabled = ref(true)
let userManager: UserManager | null = null

export function useAuth() {
  async function init() {
    const resp = await fetch('/api/auth/config')
    const config = await resp.json()
    if (!config.enabled) {
      authEnabled.value = false
      isAuthenticated.value = true
      isAuthLoading.value = false
      return
    }
    authEnabled.value = true

    // If a master token was persisted from a previous session, skip the OIDC
    // flow entirely -- the user is already considered authenticated.
    if (masterToken.value) {
      isAuthenticated.value = true
      isAuthLoading.value = false
      return
    }
    const settings: UserManagerSettings = {
      authority: config.issuer,
      client_id: config.clientId,
      redirect_uri: window.location.origin + '/callback',
      post_logout_redirect_uri: window.location.origin,
      response_type: 'code',
      scope: 'openid profile email',
      automaticSilentRenew: true,
      silent_redirect_uri: window.location.origin + '/silent-renew',
    }
    userManager = new UserManager(settings)

    if (window.location.pathname === '/callback') {
      try {
        const u = await userManager.signinRedirectCallback()
        user.value = u
        isAuthenticated.value = true
        window.history.replaceState({}, '', '/')
      } catch (e) {
        console.error('OIDC callback error:', e)
      }
      isAuthLoading.value = false
      return
    }
    if (window.location.pathname === '/silent-renew') {
      await userManager.signinSilentCallback().catch(console.error)
      return
    }
    try {
      const existing = await userManager.getUser()
      if (existing && !existing.expired) {
        user.value = existing
        isAuthenticated.value = true
      }
    } catch (e) {
      console.error('Failed to get user:', e)
    }

    userManager.events.addUserLoaded((u) => {
      user.value = u
      isAuthenticated.value = true
    })
    userManager.events.addUserUnloaded(() => {
      user.value = null
      isAuthenticated.value = false
    })
    userManager.events.addAccessTokenExpired(() => {
      user.value = null
      isAuthenticated.value = false
    })
    isAuthLoading.value = false
  }

  async function login() {
    try {
      await userManager?.signinRedirect()
    } catch (e) {
      console.error('OIDC signinRedirect error:', e)
    }
  }

  async function logout() {
    if (masterToken.value) {
      await clearSession()
      return
    }
    if (userManager) {
      await userManager.signoutRedirect()
    }
  }

  function getAccessToken(): string | null {
    // Prefer OIDC access token; fall back to master token for token-based auth
    return user.value?.access_token ?? masterToken.value ?? null
  }

  /**
   * Validates the given token against the backend and, if accepted, sets it as
   * the active credential. No OIDC user object is created -- getAccessToken()
   * returns masterToken directly. Throws if the backend rejects the token.
   */
  async function loginWithToken(token: string) {
    const resp = await fetch('/api/analysis', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (resp.status === 401) {
      throw new Error('Invalid token')
    }
    // Persist to sessionStorage so the token survives page refresh within the same tab.
    sessionStorage.setItem('master_token', token)
    masterToken.value = token
    isAuthenticated.value = true
  }

  /**
   * Clears local session state without redirecting to the OIDC provider.
   * Used when the backend returns 401 (token expired or invalid) and the
   * provider session may also be dead, which would cause a redirect loop.
   * Removes the stored user from sessionStorage and resets reactive auth state
   * so the login screen is shown immediately.
   */
  async function clearSession() {
    if (userManager) {
      await userManager.removeUser()
    }
    user.value = null
    // Remove from sessionStorage so the cleared session is not restored on refresh.
    sessionStorage.removeItem('master_token')
    masterToken.value = null
    isAuthenticated.value = false
  }

  return {
    user: readonly(user),
    isAuthenticated: readonly(isAuthenticated),
    isAuthLoading: readonly(isAuthLoading),
    authEnabled: readonly(authEnabled),
    init,
    login,
    logout,
    loginWithToken,
    getAccessToken,
    clearSession,
  }
}
