import { useQuery, useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'

const bypassAuth = import.meta.env.VITE_TEST_BYPASS_AUTH === 'true'

export type HistoryEntry = {
  _id: Id<'history'>
  question: string
  rawXml: string
  _creationTime: number
}

// E2E seam: in test-bypass builds only, Playwright can seed history via
// window.__GOLEM_E2E_HISTORY__. Vite inlines VITE_TEST_BYPASS_AUTH at build
// time, so production bundles drop this branch entirely.
function e2eSeededHistory(): HistoryEntry[] {
  return (window as { __GOLEM_E2E_HISTORY__?: HistoryEntry[] }).__GOLEM_E2E_HISTORY__ ?? []
}

export function useHistory(isGuest = false) {
  const skip = bypassAuth || isGuest
  const queried = useQuery(api.history.list, skip ? 'skip' : {}) ?? []
  const entries = bypassAuth ? e2eSeededHistory() : queried
  const addMutation = useMutation(api.history.add)
  const clearMutation = useMutation(api.history.clear)

  return {
    entries: entries as HistoryEntry[],
    save: skip
      ? async (_question: string, _rawXml: string): Promise<null> => null
      : (question: string, rawXml: string): Promise<Id<'history'>> =>
          addMutation({ question, rawXml }),
    clear: skip ? async () => {} : () => clearMutation({}),
  }
}
