import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, it, expect, vi } from 'vitest'

vi.mock('convex/react', () => ({ useMutation: () => vi.fn() }))
vi.mock('../convex/_generated/api', () => ({ api: { evals: { setFeedback: 'setFeedback-ref' } } }))

import { ResponsePanel } from '../src/components/ResponsePanel'

afterEach(cleanup)

const parsedResponse = {
  productTag: 'Verified by Golem',
  summary: 'Summary text',
  rootCause: 'Cause text',
  debugSteps: [],
  docs: [],
}

function renderPanel(isShared?: boolean) {
  return render(
    createElement(ResponsePanel, {
      isLoading: false,
      isStreaming: false,
      parsedResponse,
      error: null,
      evalId: null,
      historyId: 'h1',
      chunks: [],
      isShared,
    }),
  )
}

describe('ResponsePanel error state', () => {
  function renderError(onRetry?: () => void) {
    return render(
      createElement(ResponsePanel, {
        isLoading: false,
        isStreaming: false,
        parsedResponse: null,
        error: 'Something went wrong. Please try again.',
        evalId: null,
        historyId: null,
        chunks: [],
        onRetry,
      }),
    )
  }

  it('shows a heading and the message in one alert, with a Try again button that calls onRetry', () => {
    const onRetry = vi.fn()
    renderError(onRetry)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain("Couldn't get an answer")
    expect(alert.textContent).toContain('Something went wrong. Please try again.')
    screen.getByRole('button', { name: 'Try again' }).click()
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('omits Try again when no retry is offered', () => {
    renderError()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })
})

describe('ResponsePanel shared mode', () => {
  it('hides the product tag and feedback, and announces a shared answer', () => {
    renderPanel(true)
    expect(screen.queryByText('Verified by Golem')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Helpful' })).toBeNull()
    expect(screen.getByText('Shared answer loaded.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Share' })).toBeTruthy()
  })

  it('renders as before when not shared', () => {
    renderPanel()
    expect(screen.getByText('Verified by Golem')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Helpful' })).toBeTruthy()
    expect(screen.getByText('Answer ready.')).toBeTruthy()
  })
})
