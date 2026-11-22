import { getTurnstileToken } from './turnstile'

const GUEST_TOKEN_KEY = 'golem_guest_token'
const API_URL = import.meta.env.VITE_API_URL ?? ''

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

async function fetchGuestToken(): Promise<string> {
  // A fresh Turnstile token per mint: each one is single-use.
  const turnstileToken = await getTurnstileToken()
  const res = await fetch(`${API_URL}/guest-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ turnstile_token: turnstileToken }),
  })
  if (!res.ok) throw new Error(`Failed to fetch guest token: ${res.status}`)
  const data = await res.json()
  return data.token as string
}

export function clearGuestToken(): void {
  localStorage.removeItem(GUEST_TOKEN_KEY)
}

export async function getGuestToken(): Promise<string> {
  const stored = localStorage.getItem(GUEST_TOKEN_KEY)
  if (stored && !isTokenExpired(stored)) return stored
  const token = await fetchGuestToken()
  localStorage.setItem(GUEST_TOKEN_KEY, token)
  return token
}
