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
  // mockReset + re-resolve: vi.restoreAllMocks() in later describes strips the resolved value
  incrementMock.mockReset().mockResolvedValue(undefined)
  createEvalMock.mockReset().mockResolvedValue('eval-id')
  saveMock.mockReset().mockResolvedValue('history-id')
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

describe('useChat aborted asks', () => {
  it('an aborted older ask does not clear the loading state of the newer ask', async () => {
    let resolveSecond!: (res: Response) => void
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            const fail = () => reject(new DOMException('aborted', 'AbortError'))
            if (init.signal?.aborted) fail()
            else init.signal?.addEventListener('abort', fail)
          }),
      )
      .mockImplementationOnce(
        () => new Promise<Response>((resolve) => (resolveSecond = resolve)),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(false))

    let firstAsk!: Promise<void>
    let secondAsk!: Promise<void>
    await act(async () => {
      firstAsk = result.current.ask('first question')
      secondAsk = result.current.ask('second question')
      await firstAsk
    })

    // The first ask has settled (aborted); the second is still in flight.
    expect(result.current.isLoading).toBe(true)
    expect(result.current.error).toBeNull()

    await act(async () => {
      resolveSecond(sseResponse())
      await secondAsk
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isStreaming).toBe(false)
  })
})

describe('useChat conversation history', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function sentHistory(fetchMock: ReturnType<typeof vi.fn>, call: number) {
    return JSON.parse(fetchMock.mock.calls[call][1].body).history
  }

  it('a 429 ask leaves no orphan user turn in the next request history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 429 }))
      .mockResolvedValueOnce(sseResponse())
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(false))

    await act(async () => {
      await result.current.ask('failed question')
    })
    expect(result.current.error).toBe("You've reached the daily limit — try again tomorrow.")

    await act(async () => {
      await result.current.ask('next question')
    })

    expect(sentHistory(fetchMock, 1)).toEqual([])
  })

  it('once the window is full, the sent history still starts with a user turn', async () => {
    // A fresh Response per call: a body can only be read once
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(sseResponse()))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(false))

    for (let i = 1; i <= 11; i++) {
      await act(async () => {
        await result.current.ask(`q${i}`)
      })
    }

    const history = sentHistory(fetchMock, 10)
    expect(history).toHaveLength(18)
    expect(history[0]).toEqual({ role: 'user', content: 'q2' })
  })

  it('a successful ask adds the question and answer pair to the next request history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse())
      .mockResolvedValueOnce(new Response(null, { status: 500 }))
      .mockResolvedValueOnce(sseResponse())
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat(false))

    await act(async () => {
      await result.current.ask('q1')
    })
    await act(async () => {
      await result.current.ask('q2 fails')
    })
    await act(async () => {
      await result.current.ask('q3')
    })

    expect(sentHistory(fetchMock, 2)).toEqual([
      { role: 'user', content: 'q1' },
      { role: 'assistant', content: '<summary>ok</summary>' },
    ])
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
