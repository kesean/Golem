import { describe, it, expect } from 'vitest'
import { parseDocLink } from '../src/lib/docLink'

describe('parseDocLink', () => {
  // Existing tests
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

  // New tests for markdown links
  describe('Markdown links', () => {
    it('parses [Title](URL) format', () => {
      expect(parseDocLink('[Title](https://x.com/a)')).toEqual({
        label: 'Title',
        href: 'https://x.com/a',
      })
    })
    it('parses [URL](URL) format where label is the URL', () => {
      expect(parseDocLink('[https://a.com/x](https://a.com/x)')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
    it('ignores text before markdown link', () => {
      expect(parseDocLink('See [Docs](https://example.com/docs)')).toEqual({
        label: 'Docs',
        href: 'https://example.com/docs',
      })
    })
  })

  // New tests for parentheses in URLs
  describe('Parentheses in URLs', () => {
    it('keeps balanced parentheses in URLs', () => {
      expect(parseDocLink('Wiki: https://en.wikipedia.org/wiki/Foo_(bar)')).toEqual({
        label: 'Wiki',
        href: 'https://en.wikipedia.org/wiki/Foo_(bar)',
      })
    })
    it('keeps parentheses in query parameters', () => {
      expect(parseDocLink('See https://example.com/search?a=(2)')).toEqual({
        label: 'See',
        href: 'https://example.com/search?a=(2)',
      })
    })
    it('strips trailing ) when unbalanced in context', () => {
      expect(parseDocLink('Clerk sessions (https://clerk.com/docs/sessions)')).toEqual({
        label: 'Clerk sessions',
        href: 'https://clerk.com/docs/sessions',
      })
    })
  })

  // New tests for angle-bracket URLs
  describe('Angle-bracket URLs', () => {
    it('parses Title: <URL> format', () => {
      expect(parseDocLink('Title: <https://a.com/x>')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('handles just angle-bracket URL', () => {
      expect(parseDocLink('<https://a.com/x>')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
  })

  // New tests for label formatting
  describe('Label formatting', () => {
    it('strips leading list marker dash', () => {
      expect(parseDocLink('- Title: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('strips leading list marker asterisk', () => {
      expect(parseDocLink('* Title: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('strips leading numbered list markers', () => {
      expect(parseDocLink('1. Title: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
      expect(parseDocLink('1) Title: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('strips markdown emphasis from label', () => {
      expect(parseDocLink('**Title**: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
      expect(parseDocLink('*Title*: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
      expect(parseDocLink('_Title_: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
      expect(parseDocLink('`Title`: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('strips markdown emphasis and list markers combined', () => {
      expect(parseDocLink('- **Title**: https://a.com/x')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
  })

  // New tests for URL hardening
  describe('URL hardening and validation', () => {
    it('accepts uppercase HTTPS scheme', () => {
      expect(parseDocLink('HTTPS://A.com/x')).toEqual({
        label: 'HTTPS://A.com/x',
        href: 'HTTPS://A.com/x',
      })
    })
    it('rejects javascript: scheme', () => {
      expect(parseDocLink('javascript:alert(1)')).toEqual({
        label: 'javascript:alert(1)',
        href: null,
      })
    })
    it('rejects userinfo in URLs', () => {
      expect(parseDocLink('https://good.com@evil.com/')).toEqual({
        label: 'https://good.com@evil.com/',
        href: null,
      })
    })
    it('rejects password in URLs', () => {
      expect(parseDocLink('https://user:password@example.com/')).toEqual({
        label: 'https://user:password@example.com/',
        href: null,
      })
    })
  })

  // Trailing punctuation tests (already partially covered but ensuring it works with new logic)
  describe('Trailing punctuation handling', () => {
    it('strips common punctuation from URL end', () => {
      expect(parseDocLink('See https://a.com/x.').href).toBe('https://a.com/x')
      expect(parseDocLink('See https://a.com/x,').href).toBe('https://a.com/x')
      expect(parseDocLink('See https://a.com/x;').href).toBe('https://a.com/x')
      expect(parseDocLink('See https://a.com/x:').href).toBe('https://a.com/x')
      expect(parseDocLink('See https://a.com/x!').href).toBe('https://a.com/x')
      expect(parseDocLink('See https://a.com/x?').href).toBe('https://a.com/x')
    })
    it('loops cleanup until stable: strips punctuation after unbalanced parens', () => {
      expect(
        parseDocLink('Title (https://clerk.com/docs/sessions).')
      ).toEqual({
        label: 'Title',
        href: 'https://clerk.com/docs/sessions',
      })
    })
    it('preserves balanced parens while stripping trailing punctuation', () => {
      expect(
        parseDocLink('Wiki: https://en.wikipedia.org/wiki/Foo_(bar)).')
      ).toEqual({
        label: 'Wiki',
        href: 'https://en.wikipedia.org/wiki/Foo_(bar)',
      })
    })
  })

  describe('Backticks and asterisks around URLs', () => {
    it('strips backticks around URL', () => {
      expect(parseDocLink('`https://a.com/x`')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
    it('strips backticks with text prefix', () => {
      expect(parseDocLink('See `https://a.com/x`')).toEqual({
        label: 'See',
        href: 'https://a.com/x',
      })
    })
    it('strips double asterisks around URL', () => {
      expect(parseDocLink('**https://a.com/x**')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
    it('strips single asterisks around URL', () => {
      expect(parseDocLink('*https://a.com/x*')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
    it('strips backticks with text and handles label', () => {
      expect(parseDocLink('Title: `https://a.com/x`')).toEqual({
        label: 'Title',
        href: 'https://a.com/x',
      })
    })
    it('does not leave lone backtick or asterisk as label', () => {
      expect(parseDocLink('`https://a.com/x`')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
      expect(parseDocLink('*https://a.com/x*')).toEqual({
        label: 'https://a.com/x',
        href: 'https://a.com/x',
      })
    })
  })
})
