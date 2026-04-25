export type ParsedResponse = {
  productTag: string
  summary: string
  rootCause: string
  debugSteps: string[]
  docs: string[]
}

export type ChatMessage = { role: 'user' | 'assistant'; content: string }

export type UseChatReturn = {
  ask: (question: string) => Promise<void>
  loadFromHistory: (rawXml: string) => void
  parsedResponse: ParsedResponse | null
  isLoading: boolean
  error: string | null
  evalId: string | null
  historyId: string | null
  reset: () => void
}
