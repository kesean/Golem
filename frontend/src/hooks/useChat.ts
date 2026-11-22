import { useState, useRef, useEffect } from 'react'
import { useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import { useToken } from '../contexts/TokenContext'
import { useHistory } from './useHistory'
import { parseResponse } from '../lib/parseResponse'
import { parseSSEChunk } from '../lib/parseSSE'
import { clearGuestToken } from '../lib/guestAuth'
import type { ParsedResponse, ChatMessage, UseChatReturn, RetrievedChunk } from '../types'

const MAX_HISTORY = 20

export function useChat(isGuest = false): UseChatReturn {
  const [parsedResponse, setParsedResponse] = useState<ParsedResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [canRetry, setCanRetry] = useState(false)
  const [evalId, setEvalId] = useState<string | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [chunks, setChunks] = useState<RetrievedChunk[]>([])
  const conversationHistory = useRef<ChatMessage[]>([])
  const abortControllerRef = useRef<AbortController | null>(null)
  const lastQuestion = useRef<string | null>(null)

  const { getToken } = useToken()
  const { save: saveToHistory } = useHistory(isGuest)
  const createEval = useMutation(api.evals.createEval)

  // Abort any in-flight stream when the component unmounts, so a stray
  // fetch/reader loop doesn't keep calling setState after unmount.
  useEffect(() => {
    return () => abortControllerRef.current?.abort()
  }, [])

  async function ask(question: string): Promise<void> {
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    lastQuestion.current = question
    // False once a newer ask has started, reset() ran, or the component unmounted.
    // reset() aborts without replacing the ref, so the ref check alone misses it.
    const isCurrent = () => abortControllerRef.current === controller && !controller.signal.aborted

    setIsLoading(true)
    setIsStreaming(false)
    setError(null)
    setCanRetry(false)
    setParsedResponse(null)
    setChunks([])
    // The previous answer's eval and history ids must not follow the new answer
    setEvalId(null)
    setHistoryId(null)

    // Prior turns only. The question joins history with its answer on success,
    // so a failed or aborted ask never leaves an orphan user turn behind.
    // History is stored in whole Q/A pairs, so keep an even count: an odd cut
    // would send an assistant turn first once the window is full.
    const history = conversationHistory.current.slice(-(MAX_HISTORY - 2))

    try {
      const post = (token: string | null) =>
        fetch(`${import.meta.env.VITE_API_URL ?? ''}/ask`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ question, history }),
          signal: controller.signal,
        })

      let token = await getToken()
      if (isGuest && token === null) {
        throw new Error('GUEST_UNAVAILABLE')
      }
      let res = await post(token)
      // A guest token cached before a secret rotation is rejected with 401.
      // Drop it and retry once with a freshly fetched token.
      if (res.status === 401 && isGuest) {
        clearGuestToken()
        token = await getToken()
        if (token === null) {
          throw new Error('GUEST_UNAVAILABLE')
        }
        res = await post(token)
      }

      if (!res.ok) {
        throw new Error(res.status === 429 ? '429' : 'SERVER_ERROR')
      }
      if (!res.body) {
        throw new Error('SERVER_ERROR')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''
      let done: {
        response: string
        input_tokens: number
        output_tokens: number
        latency_ms: number
        chunks: RetrievedChunk[]
      } | null = null

      function handleEvents(chunk: string): typeof done {
        const { events, rest } = parseSSEChunk(chunk)
        buffer = rest
        let result: typeof done = null
        for (const event of events) {
          if (event.type === 'delta') {
            fullText += event.text
            if (isCurrent()) {
              setIsStreaming(true)
              setParsedResponse(parseResponse(fullText))
            }
          } else if (event.type === 'done') {
            result = event
          } else if (event.type === 'error') {
            throw new Error(event.error || 'SERVER_ERROR')
          }
        }
        return result
      }

      while (true) {
        const { value, done: streamDone } = await reader.read()
        if (streamDone) break

        buffer += decoder.decode(value, { stream: true })
        done = handleEvents(buffer) ?? done
      }
      // Flush any multi-byte UTF-8 sequence left buffered in the decoder
      // (split across the last two network chunks) and re-parse once more —
      // without this, a character split right at stream end is silently
      // dropped instead of appearing in the final response text.
      buffer += decoder.decode()
      if (buffer.trim()) {
        done = handleEvents(buffer + '\n\n') ?? done
      }

      if (!done) {
        throw new Error('SERVER_ERROR')
      }
      // A superseded ask that finishes late must not write history, response,
      // chunks, or the save/eval records that belong to the newer ask.
      if (!isCurrent()) return

      conversationHistory.current = [
        ...conversationHistory.current,
        { role: 'user' as const, content: question },
        { role: 'assistant' as const, content: done.response },
      ].slice(-MAX_HISTORY)

      setParsedResponse(parseResponse(done.response))
      // Defensive: a backend serving an older /ask response shape (e.g. mid
      // rolling-deploy) may omit "chunks" entirely from the done event.
      setChunks(done.chunks ?? [])

      if (!isGuest) {
        saveToHistory(question, done.response)
          .then(hId => { if (isCurrent()) setHistoryId(hId) })
          .catch(() => {})

        createEval({
          question,
          response: done.response,
          latency_ms: done.latency_ms,
          input_tokens: done.input_tokens,
          output_tokens: done.output_tokens,
        })
          .then(id => { if (isCurrent()) setEvalId(id) })
          .catch(() => { if (isCurrent()) setEvalId('eval-unavailable') })
      }
    } catch (err) {
      // A superseded ask must not overwrite the newer ask's error or response.
      if (abortControllerRef.current !== controller) return
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Deliberate cancellation (reset() or unmount) — not a failure,
        // so don't clobber whatever state reset() already set.
        return
      }
      const rateLimited = err instanceof Error && err.message === '429'
      const guestUnavailable = err instanceof Error && err.message === 'GUEST_UNAVAILABLE'
      const msg = rateLimited
        ? "You've reached the daily limit — try again tomorrow."
        : guestUnavailable
        ? 'Guest access is temporarily unavailable. Please sign in to continue.'
        : 'Something went wrong. Please try again.'
      // Retrying cannot help a daily limit or a missing guest session
      setCanRetry(!rateLimited && !guestUnavailable)
      setError(msg)
      setParsedResponse(null)
      setChunks([])
      if (import.meta.env.DEV) {
        console.error('[useChat] ask error:', err)
      }
    } finally {
      // Only the latest ask owns the loading state. An older ask aborted by a
      // newer one must not clear the newer ask's spinner.
      if (abortControllerRef.current === controller) {
        setIsLoading(false)
        setIsStreaming(false)
      }
    }
  }

  function loadFromHistory(rawXml: string, historyId?: string): void {
    abortControllerRef.current?.abort()
    setParsedResponse(parseResponse(rawXml))
    setEvalId(null)
    setHistoryId(historyId ?? null)
    setError(null)
    setCanRetry(false)
    // History entries predate the debug panel's per-request chunk capture
    setChunks([])
  }

  function reset(): void {
    abortControllerRef.current?.abort()
    setParsedResponse(null)
    setError(null)
    setCanRetry(false)
    setEvalId(null)
    setHistoryId(null)
    setChunks([])
  }

  // Re-asks the last question with the same prior-turn history. Only offered
  // after a failure, so the failed ask left no turn behind.
  function retry(): void {
    if (lastQuestion.current !== null) void ask(lastQuestion.current)
  }

  return {
    ask,
    retry,
    canRetry,
    loadFromHistory,
    parsedResponse,
    isLoading,
    isStreaming,
    error,
    evalId,
    historyId,
    chunks,
    reset,
  }
}
