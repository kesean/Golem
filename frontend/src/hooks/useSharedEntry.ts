import { useEffect, useState } from 'react'
import { useConvex } from 'convex/react'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'

export type SharedEntryState =
  | { status: 'none' }
  | { status: 'loading' }
  | { status: 'found'; id: string; question: string; rawXml: string }
  | { status: 'notFound' }

export type SharedView = 'none' | 'found' | 'notFound'

// Long enough for a cold Convex connection, short enough that an unreachable
// backend shows the "link doesn't work" notice instead of loading forever.
export const SHARE_TIMEOUT_MS = 8000

function readShareId(): string | null {
  return new URLSearchParams(window.location.search).get('share') || null
}

/**
 * Reads ?share=<historyId> once, strips it from the URL, and looks the entry
 * up through the public history.getById query. Never throws: a malformed id
 * (rejected by the Convex validator), a missing entry, or a timeout all
 * resolve to notFound.
 */
export function useSharedEntry(timeoutMs: number = SHARE_TIMEOUT_MS): SharedEntryState {
  const convex = useConvex()
  const [shareId] = useState(readShareId)
  const [state, setState] = useState<SharedEntryState>(() =>
    shareId ? { status: 'loading' } : { status: 'none' },
  )

  useEffect(() => {
    if (!shareId) return

    const url = new URL(window.location.href)
    url.searchParams.delete('share')
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('share lookup timed out')), timeoutMs)
    })

    Promise.race([convex.query(api.history.getById, { id: shareId as Id<'history'> }), timeout])
      .then((entry) => {
        if (cancelled) return
        setState(
          entry
            ? { status: 'found', id: shareId, question: entry.question, rawXml: entry.rawXml }
            : { status: 'notFound' },
        )
      })
      .catch((err) => {
        if (cancelled) return
        console.warn('shared answer lookup failed', err)
        setState({ status: 'notFound' })
      })
      .finally(() => clearTimeout(timer))

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [shareId, convex, timeoutMs])

  return state
}

/** What the share notice should show; nothing once the user has started their own work. */
export function sharedViewFor(state: SharedEntryState, userActed: boolean): SharedView {
  if (userActed) return 'none'
  if (state.status === 'found') return 'found'
  if (state.status === 'notFound') return 'notFound'
  return 'none'
}
