import { describe, it, expect, beforeEach } from 'vitest'
import { TOUR_STEPS, TOUR_STORAGE_KEY, hasSeenTour, markTourSeen } from '../src/lib/tour'

describe('tour', () => {
  beforeEach(() => localStorage.clear())

  it('has 3 steps with non-empty titles and bodies', () => {
    expect(TOUR_STEPS).toHaveLength(3)
    for (const s of TOUR_STEPS) {
      expect(s.title.trim()).not.toBe('')
      expect(s.body.trim()).not.toBe('')
    }
  })

  it('hasSeenTour is false initially and true after markTourSeen', () => {
    expect(hasSeenTour()).toBe(false)
    markTourSeen()
    expect(hasSeenTour()).toBe(true)
    expect(localStorage.getItem(TOUR_STORAGE_KEY)).toBe('1')
  })

  it('does not throw when localStorage is unavailable', () => {
    const orig = Storage.prototype.getItem
    try {
      Storage.prototype.getItem = () => { throw new Error('blocked') }
      expect(hasSeenTour()).toBe(true) // fail closed: never nag if storage is broken
    } finally {
      Storage.prototype.getItem = orig
    }
  })
})
