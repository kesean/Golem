import { describe, it, expect, vi, afterEach } from 'vitest'
import { readStoredTheme } from '../src/hooks/useTheme'

function systemPrefersDark(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
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
