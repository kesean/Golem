import { describe, it, expect } from 'vitest'
import { parseDocLink } from '../src/lib/docLink'

describe('parseDocLink', () => {
  it('bare URL: label is the URL, href is the URL', () => {
    expect(parseDocLink('https://docs.example.com/auth')).toEqual({
      label: 'https://docs.example.com/auth',
      href: 'https://docs.example.com/auth',
    })
  })
  it('"Title: URL" splits title and URL', () => {
    expect(
      parseDocLink('MDN - Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS'),
    ).toEqual({
      label: 'MDN - Cross-Origin Resource Sharing (CORS)',
      href: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS',
    })
  })
  it('"Title - URL" and "Title (URL)" forms', () => {
    expect(parseDocLink('Clerk sessions - https://clerk.com/docs/sessions')).toEqual({
      label: 'Clerk sessions',
      href: 'https://clerk.com/docs/sessions',
    })
    expect(parseDocLink('Clerk sessions (https://clerk.com/docs/sessions)')).toEqual({
      label: 'Clerk sessions',
      href: 'https://clerk.com/docs/sessions',
    })
  })
  it('strips trailing punctuation from the URL', () => {
    expect(parseDocLink('See https://a.com/x.').href).toBe('https://a.com/x')
  })
  it('no URL: plain text, href null', () => {
    expect(parseDocLink('Clerk session tokens overview')).toEqual({
      label: 'Clerk session tokens overview',
      href: null,
    })
  })
  it('rejects non-http(s) schemes', () => {
    expect(parseDocLink('click javascript:alert(1)').href).toBeNull()
    expect(parseDocLink('Title: ftp://x.com/y').href).toBeNull()
  })
})
