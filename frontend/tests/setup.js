/**
 * setup.js — Global stubs for the Vitest/jsdom environment.
 *
 * Runs before every test file. Stubs browser APIs that jsdom does not
 * implement and third-party globals (Convex, Clerk) that app.js expects.
 * Guards are in place so this file is safe to load in edge-runtime too.
 */
import { vi } from 'vitest'

// Only apply browser stubs in environments that have a full window (jsdom)
if (typeof window !== 'undefined' && typeof window.history !== 'undefined') {
  // navigator.clipboard is not implemented in jsdom
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
    writable: true,
  })

  // window.history.replaceState is a no-op in tests
  window.history.replaceState = vi.fn()
}
