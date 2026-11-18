import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, it, expect, vi } from 'vitest'

vi.mock('convex/react', () => ({ useQuery: () => 14 }))
vi.mock('../convex/_generated/api', () => ({ api: { stats: { getGlobalCount: 'stats:getGlobalCount' } } }))

import { Header } from '../src/components/Header'

const base = {
  theme: 'light' as const,
  onToggleTheme: vi.fn(),
  onOpenHistory: vi.fn(),
  onOpenTour: vi.fn(),
  onNewConversation: vi.fn(),
}

afterEach(cleanup)

describe('Header (signed in)', () => {
  it('renders a Sign out button and the user name', () => {
    const onSignOut = vi.fn()
    render(createElement(Header, { ...base, userName: 'Ada', onSignOut }))
    screen.getByRole('button', { name: 'Sign out' }).click()
    expect(onSignOut).toHaveBeenCalledOnce()
    expect(screen.getByText('Ada')).toBeTruthy()
  })

  it('wraps its controls on narrow screens instead of overflowing the viewport', () => {
    const { container } = render(createElement(Header, { ...base, userName: 'Ada', onSignOut: vi.fn() }))
    const header = container.querySelector('header') as HTMLElement
    // Tailwind's flex-wrap is class-based; jsdom does not apply it, so assert the class
    expect(header.className).toContain('flex-wrap')
    expect(header.style.flexWrap).toBe('')
    for (const name of ['New conversation', 'Open history (Ctrl+K)', 'Sign out']) {
      expect(screen.getByRole('button', { name })).toBeTruthy()
    }
  })

  it('omits Sign out when signed out', () => {
    render(createElement(Header, base))
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
  })
})
