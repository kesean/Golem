import { createElement } from 'react'
import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, it, expect } from 'vitest'
import { MarkdownContent } from '../src/components/SectionCard'

afterEach(cleanup)

function renderProse(content: string): HTMLElement {
  const { container } = render(createElement(MarkdownContent, { content }))
  return container.querySelector('.nb-prose') as HTMLElement
}

const ATTACK = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '<form action="https://evil.example/x"><input type="password" name="p"><button>Sign in</button></form>',
  '<div style="position:fixed;inset:0" class="fixed inset-0">cover</div>',
  '![](https://evil.example/p.png)',
  '[bad](javascript:alert(1))',
  '[ok](https://clerk.com/docs)',
  '<p aria-hidden="true" aria-label="x" data-state="open">p</p>',
  '[t](tel:123)',
  '[r](/relative)',
].join('\n\n')

describe('safeHtml hardening', () => {
  it('strips phishing, overlay, tracking and script markup', () => {
    const prose = renderProse(ATTACK)
    expect(prose.querySelector('script, img, form, input, button, [style], [class], [onerror]')).toBeNull()
    for (const a of Array.from(prose.querySelectorAll('a'))) {
      const href = a.getAttribute('href')
      if (href !== null) expect(href).toMatch(/^https:/i)
    }
    expect(prose.querySelector('a[href="tel:123"], a[href="/relative"]')).toBeNull()
    expect(prose.querySelector('[aria-hidden], [aria-label], [data-state]')).toBeNull()
  })

  it('keeps safe links and opens them in a new tab', () => {
    const prose = renderProse(ATTACK)
    const link = prose.querySelector('a[href="https://clerk.com/docs"]')
    expect(link).not.toBeNull()
    expect(link!.getAttribute('target')).toBe('_blank')
    expect(link!.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('keeps prose markup used by normal answers', () => {
    const prose = renderProse('**bold** and `code`\n\n- one\n- two\n\n```\nnpm i\n```')
    expect(prose.querySelector('strong')?.textContent).toBe('bold')
    expect(prose.querySelector('code')?.textContent).toBe('code')
    expect(prose.querySelectorAll('li')).toHaveLength(2)
    expect(prose.querySelector('pre')).not.toBeNull()
  })
})

// The sanitizer hook has no view of whether an answer is shared, so one rule
// set applies to both. Each case runs under both labels to show that.
describe.each([['shared answer'], ['own answer']])('link allowlist in a %s', (_kind) => {
  it('removes the href from a link to an unknown host, keeping its text', () => {
    const prose = renderProse('[Phish](https://evil.test/login)')
    // The anchor stays but without an href, so it is no longer a link.
    expect(prose.querySelector('a[href]')).toBeNull()
    expect(prose.textContent).toContain('Phish')
  })

  it('removes the href from a look-alike host', () => {
    const prose = renderProse('[Phish](https://clerk.com.evil.test/login)')
    expect(prose.querySelector('a[href]')).toBeNull()
  })

  it('removes the href from a userinfo trick', () => {
    const prose = renderProse('[Phish](https://clerk.com@evil.test/login)')
    expect(prose.querySelector('a[href]')).toBeNull()
  })

  it('removes mailto links for every answer', () => {
    const prose = renderProse('[Mail](mailto:someone@example.com)')
    expect(prose.querySelector('a[href]')).toBeNull()
  })

  it('keeps clerk.com and developer.mozilla.org links with target and rel set', () => {
    const prose = renderProse(
      '[Clerk](https://clerk.com/docs)\n\n[MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)',
    )
    const clerk = prose.querySelector('a[href="https://clerk.com/docs"]')
    const mdn = prose.querySelector('a[href="https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS"]')
    expect(clerk?.getAttribute('target')).toBe('_blank')
    expect(clerk?.getAttribute('rel')).toBe('noopener noreferrer')
    expect(mdn).not.toBeNull()
  })
})
