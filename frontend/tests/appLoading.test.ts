import { createElement } from 'react'
import { cleanup, render, screen, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { AppLoading, STILL_LOADING_MS } from '../src/components/AppLoading'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('AppLoading', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('shows no recovery message before the timeout', () => {
    render(createElement(AppLoading))
    act(() => {
      vi.advanceTimersByTime(STILL_LOADING_MS - 1)
    })
    expect(screen.queryByText(/Still loading/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reload' })).toBeNull()
  })

  it('after the timeout shows the message and a 44px Reload button', () => {
    render(createElement(AppLoading))
    act(() => {
      vi.advanceTimersByTime(STILL_LOADING_MS)
    })
    expect(screen.getByText('Still loading. Check your connection or reload.')).toBeTruthy()
    const reload = screen.getByRole('button', { name: 'Reload' })
    expect(reload.className).toContain('min-h-11')
  })

  it('stays a polite status region throughout', () => {
    render(createElement(AppLoading))
    expect(screen.getByRole('status').textContent).toContain('Loading…')
  })
})
