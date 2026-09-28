import { useState, useRef } from 'react'
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

  const { getToken } = useToken()
  const { save: saveToHistory } = useHistory(isGuest)
  const createEval = useMutation(api.evals.createEval)

  async function ask(question: string): Promise<void> {
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

      while (true) {
        const { value, done: streamDone } = await reader.read()
        if (streamDone) break

        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSSEChunk(buffer)
        buffer = rest

        for (const event of events) {
          if (event.type === 'delta') {
            fullText += event.text
            setIsStreaming(true)
            setParsedResponse(parseResponse(fullText))
          } else if (event.type === 'done') {
            done = event
          } else if (event.type === 'error') {
            throw new Error(event.error || 'SERVER_ERROR')
          }
        }
      }

      if (!done) {
        throw new Error('SERVER_ERROR')
      }

      conversationHistory.current = [
        ...conversationHistory.current,
        { role: 'assistant' as const, content: done.response },
      ].slice(-MAX_HISTORY)

      setParsedResponse(parseResponse(done.response))
      setChunks(done.chunks)

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

  function loadFromHistory(rawXml: string): void {
    setParsedResponse(parseResponse(rawXml))
    setEvalId(null)
    setHistoryId(null)
    setError(null)
    // History entries predate the debug panel's per-request chunk capture
    setChunks([])
  }

  function reset(): void {
    setParsedResponse(null)
    setError(null)
    setEvalId(null)
    setHistoryId(null)
    setChunks([])
  }

  return { ask, loadFromHistory, parsedResponse, isLoading, isStreaming, error, evalId, historyId, chunks, reset }
}
