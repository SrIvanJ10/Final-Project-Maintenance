/**
 * Composable – authentication state and actions.
 *
 * Owns the `user` ref and the auth-form draft state.  Depends on
 * `useFlash` for error / success messages.
 */

import { reactive, ref } from 'vue'
import * as api from '../lib/api'
import { AUTH_MODES } from '../constants.js'

/**
 * @param {object} deps
 * @param {Function} deps.setFlash
 * @param {Function} deps.onAuthenticated – callback invoked after successful login / register / boot
 */
export function useAuth({ setFlash, onAuthenticated }) {
  /** @type {import('vue').Ref<object|null>} */
  const user = ref(null)
  const status = ref('Checking session...')

  const auth = reactive({
    mode: AUTH_MODES.LOGIN,
    username: '',
    email: '',
    password: '',
  })

  /** Try to restore a session from the existing cookie. */
  async function boot() {
    try {
      const payload = await api.getCurrentUser()
      user.value = payload.user
      if (onAuthenticated) await onAuthenticated()
    } catch {
      status.value = 'Not authenticated'
    }
  }

  /** Log in with username + password. */
  async function login() {
    setFlash()
    try {
      const payload = await api.login(auth.username, auth.password)
      user.value = payload.user
      auth.password = ''
      if (onAuthenticated) await onAuthenticated()
    } catch (e) {
      setFlash('', e.message)
    }
  }

  /** Create a new account. */
  async function register() {
    setFlash()
    try {
      const payload = await api.register(auth.username, auth.email, auth.password)
      user.value = payload.user
      auth.password = ''
      auth.email = ''
      auth.mode = AUTH_MODES.LOGIN
      if (onAuthenticated) await onAuthenticated()
    } catch (e) {
      setFlash('', e.message)
    }
  }

  /** Destroy the session. */
  async function logout() {
    await api.logout()
    user.value = null
    status.value = 'Signed out'
  }

  return { user, status, auth, boot, login, register, logout }
}
