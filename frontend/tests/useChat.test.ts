import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChat } from '../src/hooks/useChat'

const incrementMock = vi.fn().mockResolvedValue(undefined)
const createEvalMock = vi.fn().mockResolvedValue('eval-id')
const saveMock = vi.fn().mockResolvedValue('history-id')

vi.mock('../convex/_generated/api', () => ({
  api: {
    evals: { createEval: 'createEval-ref' },
    stats: { increment: 'increment-ref' },
  },
}))

vi.mock('convex/react', () => ({
  useMutation: (ref: string) =>
    ref === 'increment-ref' ? incrementMock : createEvalMock,
}))

vi.mock('../src/hooks/useHistory', () => ({
  useHistory: () => ({ save: saveMock }),
}))

vi.mock('../src/contexts/TokenContext', () => ({
  useToken: () => ({ getToken: async () => 'test-token' }),
}))

function sseResponse(): Response {
  const body =
    `data: ${JSON.stringify({ type: 'delta', text: '<summary>ok</summary>' })}\n\n` +
    `data: ${JSON.stringify({
      type: 'done',
      response: '<summary>ok</summary>',
      input_tokens: 1,
      output_tokens: 1,
      latency_ms: 1,
      chunks: [],
    })}\n\n`
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

beforeEach(() => {
  incrementMock.mockClear()
  createEvalMock.mockClear()
  saveMock.mockClear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse()))
})

describe('useChat stats increment', () => {
  it('increments the global counter for a guest ask, without saving history/eval', async () => {
    const { result } = renderHook(() => useChat(true))

    await act(async () => {
      await result.current.ask('Why am I getting a 401?')
    })

    expect(incrementMock).toHaveBeenCalledTimes(1)
    expect(createEvalMock).not.toHaveBeenCalled()
    expect(saveMock).not.toHaveBeenCalled()
  })

  it('increments the global counter for a signed-in ask too', async () => {
    const { result } = renderHook(() => useChat(false))

    await act(async () => {
      await result.current.ask('Why am I getting a 401?')
    })

    expect(incrementMock).toHaveBeenCalledTimes(1)
    expect(createEvalMock).toHaveBeenCalledTimes(1)
  })
})
