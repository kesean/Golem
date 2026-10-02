import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const query = vi.fn()
const convexMock = { query }

vi.mock('../convex/_generated/api', () => ({
  api: { history: { getById: 'getById-ref' } },
}))

vi.mock('convex/react', () => ({
  useConvex: () => convexMock,
}))

import { useSharedEntry, sharedViewFor } from '../src/hooks/useSharedEntry'

afterEach(() => {
  window.history.pushState({}, '', '/')
  query.mockReset()
  vi.mocked(window.history.replaceState).mockClear()
  vi.restoreAllMocks()
})

describe('useSharedEntry', () => {
  it('is none and makes no query without a share param', () => {
    const { result } = renderHook(() => useSharedEntry())
    expect(result.current).toEqual({ status: 'none' })
    expect(query).not.toHaveBeenCalled()
  })

  it('loads a found entry and strips only the share param', async () => {
    window.history.pushState({}, '', '/?share=abc&x=1#h')
    query.mockResolvedValue({ question: 'Q', rawXml: '<summary>ok</summary>' })
    const { result } = renderHook(() => useSharedEntry())
    expect(result.current).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.status).toBe('found'))
    expect(result.current).toEqual({ status: 'found', id: 'abc', question: 'Q', rawXml: '<summary>ok</summary>' })
    expect(query).toHaveBeenCalledWith('getById-ref', { id: 'abc' })
    expect(window.history.replaceState).toHaveBeenCalledWith(window.history.state, '', '/?x=1#h')
  })

  it('strips to a bare path when share was the only param', async () => {
    window.history.pushState({}, '', '/?share=abc')
    query.mockResolvedValue(null)
    renderHook(() => useSharedEntry())
    await waitFor(() => expect(window.history.replaceState).toHaveBeenCalledWith(window.history.state, '', '/'))
  })

  it('is notFound when the entry does not exist', async () => {
    window.history.pushState({}, '', '/?share=abc')
    query.mockResolvedValue(null)
    const { result } = renderHook(() => useSharedEntry())
    await waitFor(() => expect(result.current).toEqual({ status: 'notFound' }))
  })

  it('is notFound, without throwing, when the query rejects (malformed id)', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.history.pushState({}, '', '/?share=not-a-valid-id')
    query.mockRejectedValue(new Error('ArgumentValidationError'))
    const { result } = renderHook(() => useSharedEntry())
    await waitFor(() => expect(result.current).toEqual({ status: 'notFound' }))
  })

  it('is notFound when the query never settles before the timeout', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.history.pushState({}, '', '/?share=abc')
    query.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useSharedEntry(50))
    await waitFor(() => expect(result.current).toEqual({ status: 'notFound' }))
  })
})

describe('sharedViewFor', () => {
  const found = { status: 'found' as const, id: 'a', question: 'Q', rawXml: '' }
  it('maps found/notFound and hides loading/none', () => {
    expect(sharedViewFor(found, false)).toBe('found')
    expect(sharedViewFor({ status: 'notFound' }, false)).toBe('notFound')
    expect(sharedViewFor({ status: 'loading' }, false)).toBe('none')
    expect(sharedViewFor({ status: 'none' }, false)).toBe('none')
  })
  it('is none once the user has acted, even if a result arrives', () => {
    expect(sharedViewFor(found, true)).toBe('none')
    expect(sharedViewFor({ status: 'notFound' }, true)).toBe('none')
  })
})
