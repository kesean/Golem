import { describe, it, expect } from 'vitest'
import { createHash } from 'node:crypto'
import vercelRaw from '../vercel.json?raw'
import indexHtml from '../index.html?raw'

const vercelConfig = JSON.parse(vercelRaw)

function headersFor(source: string): Record<string, string> {
  const rule = vercelConfig.headers.find((h: { source: string }) => h.source === source)
  expect(rule, `no headers rule for ${source}`).toBeDefined()
  return Object.fromEntries(rule.headers.map((h: { key: string; value: string }) => [h.key, h.value]))
}

function directives(csp: string): Map<string, string[]> {
  return new Map(
    csp
      .split(';')
      .map((d) => d.trim())
      .filter(Boolean)
      .map((d) => {
        const [name, ...values] = d.split(/\s+/)
        return [name, values] as const
      }),
  )
}

// Inline (no src) classic scripts in index.html. Module scripts with src are covered by 'self'.
function inlineScripts(html: string): string[] {
  const re = /<script(\s[^>]*)?>([\s\S]*?)<\/script>/g
  const out: string[] = []
  for (const m of html.matchAll(re)) {
    const attrs = m[1] ?? ''
    if (/\ssrc=/.test(attrs)) continue
    out.push(m[2])
  }
  return out
}

describe('security headers (vercel.json)', () => {
  const headers = headersFor('/(.*)')
  const csp = headers['Content-Security-Policy']
  const d = directives(csp)

  it('applies the CSP and the other security headers to all routes', () => {
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['Referrer-Policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['Permissions-Policy']).toBe('camera=(), microphone=(), geolocation=(), payment=()')
  })

  it('keeps the locked-down baseline directives', () => {
    expect(d.get('default-src')).toEqual(["'self'"])
    expect(d.get('object-src')).toEqual(["'none'"])
    expect(d.get('base-uri')).toEqual(["'self'"])
    expect(d.get('form-action')).toEqual(["'self'"])
    expect(d.get('frame-ancestors')).toEqual(["'none'"])
  })

  it('has exactly one inline script in index.html and its sha256 hash is allowed in script-src', () => {
    const inline = inlineScripts(indexHtml)
    expect(inline, 'index.html must have exactly one inline script; update the CSP hash if it changes').toHaveLength(1)
    const hash = `'sha256-${createHash('sha256').update(inline[0]).digest('base64')}'`
    expect(d.get('script-src')).toContain(hash)
  })

  it('allows the Clerk and Cloudflare Turnstile hosts Clerk requires', () => {
    expect(d.get('script-src')).toEqual(
      expect.arrayContaining(['https://*.clerk.accounts.dev', 'https://*.protect.clerk.com', 'https://challenges.cloudflare.com']),
    )
    expect(d.get('connect-src')).toEqual(expect.arrayContaining(['https://*.clerk.accounts.dev', 'https://*.protect.clerk.com:*']))
    expect(d.get('frame-src')).toEqual(expect.arrayContaining(['https://challenges.cloudflare.com', 'https://*.protect.clerk.com']))
    expect(d.get('worker-src')).toEqual(expect.arrayContaining(["'self'", 'blob:']))
    expect(d.get('img-src')).toContain('https://img.clerk.com')
  })

  it('allows the API origin and the Convex origin over https and wss', () => {
    expect(d.get('connect-src')).toEqual(
      expect.arrayContaining(["'self'", 'https://golem-api.vercel.app', 'https://*.convex.cloud', 'wss://*.convex.cloud']),
    )
  })

  it('allows only the Google Fonts origins for remote styles and fonts', () => {
    expect(d.get('style-src')).toEqual(["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'])
    expect(d.get('font-src')).toEqual(["'self'", 'https://fonts.gstatic.com'])
  })
})
