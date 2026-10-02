import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, it, expect, vi } from 'vitest'
import { SharedNotice } from '../src/components/SharedNotice'

afterEach(cleanup)

const FOUND = "Shared by another user. It wasn't generated for you and may have been edited."
const NOT_FOUND = "This shared link doesn't work. The answer may have been deleted."

describe('SharedNotice', () => {
  it('always mounts an empty status region when there is nothing to show', () => {
    render(createElement(SharedNotice, { view: 'none', onAskOwn: vi.fn() }))
    expect(screen.getByRole('status').textContent).toBe('')
  })

  it('shows the provenance copy inside the status region when found', () => {
    render(createElement(SharedNotice, { view: 'found', onAskOwn: vi.fn() }))
    expect(screen.getByRole('status').textContent).toContain(FOUND)
  })

  it('shows the broken-link copy when notFound', () => {
    render(createElement(SharedNotice, { view: 'notFound', onAskOwn: vi.fn() }))
    expect(screen.getByRole('status').textContent).toContain(NOT_FOUND)
  })

  it('calls onAskOwn from the button', () => {
    const onAskOwn = vi.fn()
    render(createElement(SharedNotice, { view: 'found', onAskOwn }))
    screen.getByRole('button', { name: 'Ask your own question' }).click()
    expect(onAskOwn).toHaveBeenCalledOnce()
  })
})
