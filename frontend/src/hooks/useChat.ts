import { useState, useRef } from 'react'
import { useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import { useToken } from '../contexts/TokenContext'
import { useHistory } from './useHistory'
import { parseResponse } from '../lib/parseResponse'
import type { ParsedResponse, ChatMessage, UseChatReturn } from '../types'

const MAX_HISTORY = 20

export function useChat(isGuest = false): UseChatReturn {
  const [parsedResponse, setParsedResponse] = useState<ParsedResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [evalId, setEvalId] = useState<string | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const conversationHistory = useRef<ChatMessage[]>([])

  const { getToken } = useToken()
  const { save: saveToHistory } = useHistory(isGuest)
  const createEval = useMutation(api.evals.createEval)

  async function ask(question: string): Promise<void> {
    setIsLoading(true)
    setError(null)
    setParsedResponse(null)

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

      const data = await res.json()
      const parsed = parseResponse(data.response)

      conversationHistory.current = [
        ...conversationHistory.current,
        { role: 'assistant' as const, content: data.response },
      ].slice(-MAX_HISTORY)

      setParsedResponse(parsed)

      if (!isGuest) {
        saveToHistory(question, data.response)
          .then(hId => setHistoryId(hId))
          .catch(() => {})

        createEval({
          question,
          response: data.response,
          latency_ms: data.latency_ms,
          input_tokens: data.input_tokens,
          output_tokens: data.output_tokens,
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
      if (import.meta.env.DEV) {
        console.error('[useChat] ask error:', err)
      }
    } finally {
      setIsLoading(false)
    }
  }

  function loadFromHistory(rawXml: string): void {
    setParsedResponse(parseResponse(rawXml))
    setEvalId(null)
    setHistoryId(null)
    setError(null)
  }

  function reset(): void {
    setParsedResponse(null)
    setError(null)
    setEvalId(null)
    setHistoryId(null)
  }

  return { ask, loadFromHistory, parsedResponse, isLoading, error, evalId, historyId, reset }
}
