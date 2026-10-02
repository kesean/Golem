import { useState, useRef, useEffect } from 'react'
import { useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import { useToken } from '../contexts/TokenContext'
import { useHistory } from './useHistory'
import { parseResponse } from '../lib/parseResponse'
import { parseSSEChunk } from '../lib/parseSSE'
import type { ParsedResponse, ChatMessage, UseChatReturn, RetrievedChunk } from '../types'

const MAX_HISTORY = 20

export function useChat(isGuest = false): UseChatReturn {
  const [parsedResponse, setParsedResponse] = useState<ParsedResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [evalId, setEvalId] = useState<string | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [chunks, setChunks] = useState<RetrievedChunk[]>([])
  const conversationHistory = useRef<ChatMessage[]>([])
  const abortControllerRef = useRef<AbortController | null>(null)

  const { getToken } = useToken()
  const { save: saveToHistory } = useHistory(isGuest)
  const createEval = useMutation(api.evals.createEval)
  const incrementStats = useMutation(api.stats.increment)

  // Abort any in-flight stream when the component unmounts, so a stray
  // fetch/reader loop doesn't keep calling setState after unmount.
  useEffect(() => {
    return () => abortControllerRef.current?.abort()
  }, [])

  async function ask(question: string): Promise<void> {
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsLoading(true)
    setIsStreaming(false)
    setError(null)
    setParsedResponse(null)
    setChunks([])

    conversationHistory.current = [
      ...conversationHistory.current,
      { role: 'user' as const, content: question },
    ].slice(-MAX_HISTORY)

    try {
      const token = await getToken()
      if (isGuest && token === null) {
        throw new Error('GUEST_UNAVAILABLE')
      }
      const res = await fetch(`${import.meta.env.VITE_API_URL ?? ''}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          history: conversationHistory.current.slice(0, -1),
        }),
        signal: controller.signal,
      })

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
            setIsStreaming(true)
            setParsedResponse(parseResponse(fullText))
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

      conversationHistory.current = [
        ...conversationHistory.current,
        { role: 'assistant' as const, content: done.response },
      ].slice(-MAX_HISTORY)

      setParsedResponse(parseResponse(done.response))
      // Defensive: a backend serving an older /ask response shape (e.g. mid
      // rolling-deploy) may omit "chunks" entirely from the done event.
      setChunks(done.chunks ?? [])

      // Unconditional — unlike history/eval below, the global counter
      // includes guest usage, since a demo visitor is almost always a guest.
      incrementStats({}).catch((err) => {
        // Non-fatal to the user, but log so a silently missed count is diagnosable
        console.warn('stats increment failed', err)
      })

      if (!isGuest) {
        saveToHistory(question, done.response)
          .then(hId => setHistoryId(hId))
          .catch(() => {})

        createEval({
          question,
          response: done.response,
          latency_ms: done.latency_ms,
          input_tokens: done.input_tokens,
          output_tokens: done.output_tokens,
        })
          .then(id => setEvalId(id))
          .catch(() => { setEvalId('eval-unavailable') })
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Deliberate cancellation (reset() or unmount) — not a failure,
        // so don't clobber whatever state reset() already set.
        return
      }
      const msg =
        err instanceof Error && err.message === '429'
          ? "You've reached the daily limit — try again tomorrow."
          : err instanceof Error && err.message === 'GUEST_UNAVAILABLE'
          ? 'Guest access is temporarily unavailable. Please sign in to continue.'
          : 'Something went wrong. Please try again.'
      setError(msg)
      setParsedResponse(null)
      setChunks([])
      if (import.meta.env.DEV) {
        console.error('[useChat] ask error:', err)
      }
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
    }
  }

  function loadFromHistory(rawXml: string, historyId?: string): void {
    abortControllerRef.current?.abort()
    setParsedResponse(parseResponse(rawXml))
    setEvalId(null)
    setHistoryId(historyId ?? null)
    setError(null)
    // History entries predate the debug panel's per-request chunk capture
    setChunks([])
  }

  function reset(): void {
    abortControllerRef.current?.abort()
    setParsedResponse(null)
    setError(null)
    setEvalId(null)
    setHistoryId(null)
    setChunks([])
  }

  return { ask, loadFromHistory, parsedResponse, isLoading, isStreaming, error, evalId, historyId, chunks, reset }
}
