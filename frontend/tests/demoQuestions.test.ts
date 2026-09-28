import { describe, it, expect } from 'vitest'
import { DEMO_QUESTIONS } from '../src/lib/demoQuestions'

describe('DEMO_QUESTIONS', () => {
  it('has exactly 5 entries', () => {
    expect(DEMO_QUESTIONS).toHaveLength(5)
  })
  it('has unique, non-empty labels and questions', () => {
    const labels = DEMO_QUESTIONS.map(q => q.label)
    const questions = DEMO_QUESTIONS.map(q => q.question)
    expect(new Set(labels).size).toBe(5)
    expect(new Set(questions).size).toBe(5)
    for (const q of DEMO_QUESTIONS) {
      expect(q.label.trim()).not.toBe('')
      expect(q.question.trim()).not.toBe('')
    }
  })
})
