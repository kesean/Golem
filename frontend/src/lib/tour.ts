export const TOUR_STORAGE_KEY = 'golem-tour-seen'

export type TourStep = { title: string; body: string }

export const TOUR_STEPS: TourStep[] = [
  {
    title: 'Ask a technical question',
    body: 'Describe an auth, CORS, streaming or rate-limit problem in plain English, or tap one of the suggested questions to try it instantly.',
  },
  {
    title: 'Get a structured answer',
    body: 'Golem replies with a summary, root cause, debug steps and relevant docs, tagged with a product area so you can scan it at a glance. Answers are grounded in retrieved Clerk and MDN docs.',
  },
  {
    title: 'History, feedback and live stats',
    body: 'Press Ctrl+K to reopen past questions (sign in to save them), rate answers with the thumbs, and watch the global counter in the header tick up as people ask.',
  },
]

export function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(TOUR_STORAGE_KEY) === '1'
  } catch {
    return true
  }
}

export function markTourSeen(): void {
  try {
    localStorage.setItem(TOUR_STORAGE_KEY, '1')
  } catch {
    // storage unavailable — nothing to persist
  }
}
