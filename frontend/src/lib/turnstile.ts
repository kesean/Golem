// Cloudflare Turnstile for the guest-token request. The widget is invisible and
// runs in execute mode, so guests see no challenge unless Cloudflare asks for one.
// The script is loaded from src (never inline), so the CSP script hash is unaffected.

const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY ?? ''
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
// The backend refuses tokens whose action differs (app.py TURNSTILE_EXPECTED_ACTION).
const TURNSTILE_ACTION = 'guest_token'

interface TurnstileApi {
  render(
    container: HTMLElement,
    options: {
      sitekey: string
      action: string
      size: 'invisible'
      callback: (token: string) => void
      'error-callback': () => void
      'expired-callback': () => void
    },
  ): string
  execute(container: HTMLElement, options?: { widgetId?: string }): void
  remove(widgetId: string): void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let scriptLoad: Promise<void> | null = null

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve()
  if (!scriptLoad) {
    scriptLoad = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = SCRIPT_URL
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => {
        scriptLoad = null
        reject(new Error('Turnstile script failed to load'))
      }
      document.head.appendChild(script)
    })
  }
  return scriptLoad
}

// Returns a fresh single-use token, or null when no site key is configured.
// The backend refuses a null token in production, so a missing key fails loudly there.
export async function getTurnstileToken(): Promise<string | null> {
  if (!SITE_KEY) return null
  await loadScript()
  const turnstile = window.turnstile
  if (!turnstile) throw new Error('Turnstile is not available')

  const container = document.createElement('div')
  container.style.display = 'none'
  document.body.appendChild(container)

  return new Promise<string>((resolve, reject) => {
    let widgetId = ''
    const cleanup = () => {
      if (widgetId) turnstile.remove(widgetId)
      container.remove()
    }
    widgetId = turnstile.render(container, {
      sitekey: SITE_KEY,
      action: TURNSTILE_ACTION,
      size: 'invisible',
      callback: (token) => {
        cleanup()
        resolve(token)
      },
      'error-callback': () => {
        cleanup()
        reject(new Error('Turnstile challenge failed'))
      },
      'expired-callback': () => {
        cleanup()
        reject(new Error('Turnstile token expired'))
      },
    })
    turnstile.execute(container, { widgetId })
  })
}
