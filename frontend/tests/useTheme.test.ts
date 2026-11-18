import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { readStoredTheme, useTheme } from '../src/hooks/useTheme'

function systemPrefersDark(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
})

describe('useTheme persistence', () => {
  it('does not write the OS-derived default to storage on mount', () => {
    systemPrefersDark(true)
    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('theme')).toBeNull()
  })

  it('stores the choice only when the user toggles, and it then wins over the OS', () => {
    systemPrefersDark(true)
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggle())

    expect(result.current.theme).toBe('light')
    expect(localStorage.getItem('theme')).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})

describe('readStoredTheme', () => {
  it('uses the stored choice over the OS preference', () => {
    systemPrefersDark(true)
    localStorage.setItem('theme', 'light')
    expect(readStoredTheme()).toBe('light')
  })

  it('falls back to the OS preference when nothing is stored', () => {
    systemPrefersDark(true)
    expect(readStoredTheme()).toBe('dark')
  })

  it('ignores an unknown stored value and uses the OS preference', () => {
    systemPrefersDark(false)
    localStorage.setItem('theme', 'sepia')
    expect(readStoredTheme()).toBe('light')
  })

  it('falls back to the OS preference when storage throws', () => {
    systemPrefersDark(true)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    expect(readStoredTheme()).toBe('dark')
  })
})
