export type DocLink = { label: string; href: string | null }

const URL_RE = /https?:\/\/[^\s<>"')\]]+/i

export function parseDocLink(raw: string): DocLink {
  const text = raw.trim()
  const match = text.match(URL_RE)
  if (!match) return { label: text, href: null }

  const href = match[0].replace(/[.,;:!?]+$/, '')
  const before = text
    .slice(0, match.index)
    .replace(/[\s:(\-–—]+$/, '')
    .trim()
  return { label: before || href, href }
}
