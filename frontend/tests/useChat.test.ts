import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

const { getTokenMock, clearGuestTokenMock } = vi.hoisted(() => ({
  getTokenMock: vi.fn(),
  clearGuestTokenMock: vi.fn(),
}))

vi.mock('../src/contexts/TokenContext', () => ({
  useToken: () => ({ getToken: getTokenMock }),
}))

vi.mock('../src/lib/guestAuth', () => ({
  clearGuestToken: clearGuestTokenMock,
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
  getTokenMock.mockReset().mockResolvedValue('test-token')
  clearGuestTokenMock.mockClear()
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

describe('useChat rejected token', () => {
  beforeEach(() => {
    // The 401 paths log the expected failure in DEV; keep test output quiet
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('a guest ask that gets 401 clears the stored token and retries once with a fresh token', async () => {
    getTokenMock.mockReset().mockResolvedValueOnce('stale').mockResolvedValueOnce('fresh')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(sseResponse())
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(true))

    await act(async () => {
      await result.current.ask('Why am I getting a 401?')
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer fresh')
    expect(clearGuestTokenMock).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBeNull()
    expect(result.current.parsedResponse?.summary).toBe('ok')
  })

  it('a guest ask that gets 401 twice shows an error without a third request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(true))

    await act(async () => {
      await result.current.ask('Why am I getting a 401?')
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.error).toBe('Something went wrong. Please try again.')
  })

  it('a signed-in ask that gets 401 does not retry', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(null, { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(false))

    await act(async () => {
      await result.current.ask('Why am I getting a 401?')
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(clearGuestTokenMock).not.toHaveBeenCalled()
    expect(result.current.error).toBe('Something went wrong. Please try again.')
  })
})

describe('useChat loadFromHistory', () => {
  it('sets historyId when one is given, and leaves evalId null', () => {
    const { result } = renderHook(() => useChat(false))
    act(() => result.current.loadFromHistory('<summary>ok</summary>', 'h1'))
    expect(result.current.historyId).toBe('h1')
    expect(result.current.evalId).toBeNull()
    expect(result.current.parsedResponse?.summary).toBe('ok')
  })

  it('clears historyId when none is given', () => {
    const { result } = renderHook(() => useChat(false))
    act(() => result.current.loadFromHistory('<summary>ok</summary>', 'h1'))
    act(() => result.current.loadFromHistory('<summary>ok</summary>'))
    expect(result.current.historyId).toBeNull()
  })
})
