const GUEST_TOKEN_KEY = 'dev_support_guest_token'
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
  const res = await fetch(`${API_URL}/guest-token`)
  if (!res.ok) throw new Error(`Failed to fetch guest token: ${res.status}`)
  const data = await res.json()
  return data.token as string
}

export async function getGuestToken(): Promise<string> {
  const stored = localStorage.getItem(GUEST_TOKEN_KEY)
  if (stored && !isTokenExpired(stored)) return stored
  const token = await fetchGuestToken()
  localStorage.setItem(GUEST_TOKEN_KEY, token)
  return token
}
