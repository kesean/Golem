import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, it, expect, vi } from 'vitest'
import { SharedNotice } from '../src/components/SharedNotice'

afterEach(cleanup)

const FOUND = "Shared by another user. It wasn't generated for you and may have been edited. Not verified by Golem."
const NOT_FOUND = 'This answer may have been deleted by its owner or removed to make room.'

describe('SharedNotice', () => {
  it('always mounts an empty status region when there is nothing to show', () => {
    render(createElement(SharedNotice, { view: 'none', onAskOwn: vi.fn() }))
    expect(screen.getByRole('status').textContent).toBe('')
  })

  it('shows the provenance copy inside the status region when found', () => {
    render(createElement(SharedNotice, { view: 'found', onAskOwn: vi.fn() }))
    expect(screen.getByRole('status').textContent).toContain(FOUND)
  })

  it('states both that another user shared it and that Golem did not verify it', () => {
    render(createElement(SharedNotice, { view: 'found', onAskOwn: vi.fn() }))
    const text = screen.getByRole('status').textContent ?? ''
    expect(text).toMatch(/shared by another user/i)
    expect(text).toMatch(/not verified by golem/i)
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
