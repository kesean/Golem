import { createElement } from 'react'
import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import type { SharedEntryState } from '../src/hooks/useSharedEntry'

let sharedState: SharedEntryState = { status: 'none' }

vi.mock('../src/hooks/useSharedEntry', async () => {
  const actual = await vi.importActual<typeof import('../src/hooks/useSharedEntry')>(
    '../src/hooks/useSharedEntry',
  )
  return { ...actual, useSharedEntry: () => sharedState }
})

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({ isSignedIn: false, isLoaded: true, user: null }),
  useClerk: () => ({ signOut: vi.fn() }),
  SignInButton: ({ children }: { children?: unknown }) => children ?? null,
}))

vi.mock('convex/react', () => ({
  useQuery: () => undefined,
  useMutation: () => vi.fn().mockResolvedValue(null),
  useConvex: () => ({ query: vi.fn() }),
}))

vi.mock('../convex/_generated/api', () => ({
  api: {
    history: { list: 'h-list', add: 'h-add', clear: 'h-clear', getById: 'h-get' },
    evals: { createEval: 'e-create', setFeedback: 'e-fb' },
    stats: { increment: 'increment', getGlobalCount: 'count' },
  },
}))

vi.mock('../src/contexts/TokenContext', () => ({
  useToken: () => ({ getToken: async () => null }),
}))

import App from '../src/App'

const RAW_XML =
  '<product_tag>Verified by Golem</product_tag><summary>Shared summary</summary><root_cause>Cause</root_cause><debug_steps></debug_steps><docs></docs>'
const FOUND_TEXT = "Shared by another user. It wasn't generated for you and may have been edited."
const NOT_FOUND_TEXT = "This shared link doesn't work. The answer may have been deleted."

const found: SharedEntryState = { status: 'found', id: 'abc', question: 'Shared question?', rawXml: RAW_XML }

function question(): HTMLTextAreaElement {
  return document.getElementById('question') as HTMLTextAreaElement
}

beforeEach(() => {
  localStorage.setItem('golem-tour-seen', '1')
  sharedState = { status: 'none' }
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network in tests')))
  if (!window.matchMedia) {
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: false, media: q, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  }
  if (!('ResizeObserver' in globalThis)) {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  }
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App shared answer state machine', () => {
  it('shows a found shared answer with provenance notice and no feedback buttons', () => {
    sharedState = found
    render(createElement(App))
    expect(question().value).toBe('Shared question?')
    expect(screen.getByText(FOUND_TEXT)).toBeTruthy()
    expect(screen.getByText('Shared summary')).toBeTruthy()
    expect(screen.queryByText('Verified by Golem')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Helpful' })).toBeNull()
  })

  it('keeps the notice when the user edits the question', () => {
    sharedState = found
    render(createElement(App))
    fireEvent.change(question(), { target: { value: 'edited' } })
    expect(screen.getByText(FOUND_TEXT)).toBeTruthy()
    expect(screen.getByText('Shared summary')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Helpful' })).toBeNull()
  })

  it('clears the shared answer on "Ask your own question"', () => {
    sharedState = found
    render(createElement(App))
    fireEvent.click(screen.getByRole('button', { name: 'Ask your own question' }))
    expect(screen.queryByText(FOUND_TEXT)).toBeNull()
    expect(screen.queryByText('Shared summary')).toBeNull()
    expect(question().value).toBe('')
  })

  it('ignores a late share result once the user has typed', () => {
    sharedState = { status: 'loading' }
    const { rerender } = render(createElement(App))
    fireEvent.change(question(), { target: { value: 'my own' } })
    sharedState = found
    rerender(createElement(App))
    expect(question().value).toBe('my own')
    expect(screen.queryByText('Shared summary')).toBeNull()
    expect(screen.queryByText(FOUND_TEXT)).toBeNull()
  })

  it('shows the notFound notice in an always-mounted status region', () => {
    const { container, rerender } = render(createElement(App))
    const empty = Array.from(container.querySelectorAll('[role="status"]')).filter(
      (el) => el.textContent === '',
    )
    expect(empty.length).toBeGreaterThan(0)
    sharedState = { status: 'notFound' }
    rerender(createElement(App))
    const region = screen.getByText(NOT_FOUND_TEXT).closest('[role="status"]')
    expect(region).not.toBeNull()
    expect(empty).toContain(region)
  })
})
