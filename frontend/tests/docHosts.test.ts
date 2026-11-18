import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, it, expect } from 'vitest'
import { isAllowedDocHref } from '../src/lib/docHosts'
import { DocList } from '../src/components/SectionCard'

afterEach(cleanup)

describe('isAllowedDocHref', () => {
  it.each([
    'https://clerk.com/docs',
    'https://clerk.com',
    'https://docs.clerk.com/auth',
    'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS',
    'https://CLERK.COM/docs',
  ])('allows %s', (href) => {
    expect(isAllowedDocHref(href)).toBe(true)
  })

  it.each([
    // Look-alike hosts
    'https://clerk.com.evil.test/docs',
    'https://evilclerk.com/docs',
    'https://developer.mozilla.org.evil.test/en-US/docs',
    'https://evil.test/clerk.com',
    'https://evil.test/?x=https://clerk.com',
    // Unicode look-alike ("с" is Cyrillic): the parsed host is punycode, not clerk.com
    'https://сlerk.com/docs',
    // Trailing dot is a different hostname string
    'https://clerk.com./docs',
    // Userinfo tricks
    'https://clerk.com@evil.test/docs',
    'https://evil.test@clerk.com/docs',
    'https://clerk.com:secret@evil.test/docs',
    // Backslash is a path separator for https, so the host is evil.test
    'https://evil.test\\@clerk.com/docs',
    // Scheme and port
    'http://clerk.com/docs',
    'https://clerk.com:8443/docs',
    'javascript:alert(1)',
    'data:text/html,<a>x</a>',
    // Not a URL at all
    'clerk.com/docs',
    '',
  ])('rejects %s', (href) => {
    expect(isAllowedDocHref(href)).toBe(false)
  })
})

describe('DocList', () => {
  it('renders only allowlisted hosts as links and everything else as plain text', () => {
    render(
      createElement(DocList, {
        docs: [
          '[MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)',
          '[Phish](https://clerk.com.evil.test/login)',
          'Userinfo: https://clerk.com@evil.test/x',
        ],
      }),
    )
    const links = Array.from(document.querySelectorAll('a'))
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS',
    ])
    expect(screen.getByText('Phish').tagName).not.toBe('A')
    expect(document.querySelector('a[href*="evil.test"]')).toBeNull()
  })
})
