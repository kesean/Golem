import { useQuery, useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'

export type HistoryEntry = {
  _id: Id<'history'>
  question: string
  rawXml: string
  _creationTime: number
}

export function useHistory() {
  const entries = useQuery(api.history.list) ?? []
  const addMutation = useMutation(api.history.add)
  const clearMutation = useMutation(api.history.clear)

  return {
    entries: entries as HistoryEntry[],
    save: (question: string, rawXml: string): Promise<Id<'history'>> =>
      addMutation({ question, rawXml }),
    clear: () => clearMutation({}),
  }
}
