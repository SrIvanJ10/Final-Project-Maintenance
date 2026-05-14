/**
 * Composable – flash / toast messages.
 *
 * Encapsulates the success / error notification system that was
 * previously a module-level side-effect with a raw `setTimeout` (TD-11).
 * The timer is now cleaned up automatically via `onUnmounted`.
 */

import { ref, onUnmounted } from 'vue'

export function useFlash() {
  const msg = ref('')
  const err = ref('')
  let flashTimeoutId = null

  /**
   * Show a flash message.  If both arguments are empty the current
   * message is cleared immediately.
   *
   * @param {string} [nextMsg='']
   * @param {string} [nextErr='']
   */
  function setFlash(nextMsg = '', nextErr = '') {
    if (flashTimeoutId) {
      clearTimeout(flashTimeoutId)
      flashTimeoutId = null
    }
    msg.value = nextMsg
    err.value = nextErr

    if (nextMsg || nextErr) {
      flashTimeoutId = window.setTimeout(() => {
        msg.value = ''
        err.value = ''
        flashTimeoutId = null
      }, 5000)
    }
  }

  /** Dismiss the current flash immediately. */
  function dismissFlash() {
    if (flashTimeoutId) {
      clearTimeout(flashTimeoutId)
      flashTimeoutId = null
    }
    msg.value = ''
    err.value = ''
  }

  /**
   * Generic wrapper that clears previous flashes, runs an async
   * function, and sets a success or error flash afterwards (TD-07).
   *
   * @param {Function} fn        – async function to execute
   * @param {string}   [okMsg]   – optional success message
   */
  async function withFlash(fn, okMsg) {
    setFlash()
    try {
      await fn()
      if (okMsg) setFlash(okMsg)
    } catch (e) {
      setFlash('', e.message)
    }
  }

  // Clean up any pending timer when the component is destroyed.
  onUnmounted(() => {
    if (flashTimeoutId) {
      clearTimeout(flashTimeoutId)
      flashTimeoutId = null
    }
  })

  return { msg, err, setFlash, dismissFlash, withFlash }
}
