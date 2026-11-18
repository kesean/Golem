import { describe, it, expect, vi, afterEach } from 'vitest'
import { createElement } from 'react'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { HistoryPalette } from '../src/components/HistoryPalette'

// Clerk's real SignInButton needs a ClerkProvider; pass the child through so the
// test sees only the child's onClick, which Clerk also runs before opening its modal.
vi.mock('@clerk/clerk-react', () => ({
  SignInButton: ({ children }: { children: unknown }) => children,
}))

vi.mock('../src/hooks/useHistory', () => ({
  useHistory: () => ({ entries: [], save: vi.fn() }),
}))

afterEach(() => {
  cleanup()
})

describe('HistoryPalette guest dialog', () => {
  it('closes the dialog when Sign in is clicked, before Clerk opens its modal', () => {
    const onOpenChange = vi.fn()
    render(
      createElement(HistoryPalette, {
        open: true,
        onOpenChange,
        onSelect: vi.fn(),
        isGuest: true,
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
