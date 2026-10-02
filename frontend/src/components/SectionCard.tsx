import React, { useId, useState } from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ExternalLink } from 'lucide-react'
import { parseDocLink } from '../lib/docLink'

// Answers can be authored by another user (share links), so only plain prose
// markup survives: no forms, images, styles or classes that could phish,
// track, or overlay the app's own UI.
const ALLOWED_TAGS = ['p', 'a', 'code', 'pre', 'strong', 'em', 'del', 'ul', 'ol', 'li', 'blockquote',
  'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tr', 'th', 'td']
const ALLOWED_ATTR = ['href', 'title']
const SAFE_HREF = /^(https?:|mailto:)/i

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName !== 'A') return
  const href = node.getAttribute('href')
  if (href !== null && !SAFE_HREF.test(href)) node.removeAttribute('href')
  node.setAttribute('target', '_blank')
  node.setAttribute('rel', 'noopener noreferrer')
})

function safeHtml(markdown: string): string {
  return DOMPurify.sanitize(marked.parse(markdown) as string, { ALLOWED_TAGS, ALLOWED_ATTR })
}

type NotebookRowProps = {
  label: string
  /** Highlighter behind the label: marks the row the reader should look at first. */
  marked?: boolean
  children: React.ReactNode
}

/** One labelled row of the answer document: label in the margin, content beside it. */
export function NotebookRow({ label, marked: isMarked, children }: NotebookRowProps) {
  return (
    <section className="nb-row">
      <h2 className={isMarked ? 'nb-label nb-label-marked' : 'nb-label'}>
        <span>{label}</span>
      </h2>
      <div className="nb-body">{children}</div>
    </section>
  )
}

export function MarkdownContent({ content }: { content: string }) {
  return <div className="nb-prose" dangerouslySetInnerHTML={{ __html: safeHtml(content) }} />
}

const STEP_PREFIX = /^\s*step\s*\d+\s*[:.)-]\s*/i

/** Steps the reader can tick off; the list numbering replaces the model's "Step N:" prefix. */
export function StepList({ steps }: { steps: string[] }) {
  // Keyed by step text so ticks can't stick to a different step as streamed output re-splits
  const [done, setDone] = useState<Record<string, boolean>>({})
  const idBase = useId()
  return (
    <ol className="nb-steps">
      {steps.map((raw, i) => {
        const text = raw.replace(STEP_PREFIX, '')
        const checked = !!done[text]
        const textId = `${idBase}-${i}`
        return (
          <li
            key={i}
            className={checked ? 'nb-step nb-step-done' : 'nb-step'}
            style={{ '--i': Math.min(i, 5) } as React.CSSProperties}
          >
            <label className="nb-step-main">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => setDone((d) => ({ ...d, [text]: !d[text] }))}
                aria-labelledby={textId}
              />
              <span className="nb-step-num" aria-hidden="true">{i + 1}</span>
              <span id={textId} className="nb-step-text nb-prose" dangerouslySetInnerHTML={{ __html: safeHtml(text) }} />
            </label>
            <CopyStep text={text} />
          </li>
        )
      })}
    </ol>
  )
}

function CopyStep({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }
  return (
    <button type="button" className="nb-copy" onClick={copy} aria-label="Copy this step">
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function hostOf(href: string): string {
  try {
    return new URL(href).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

export function DocList({ docs }: { docs: string[] }) {
  return (
    <ul className="nb-docs">
      {docs.map((doc, i) => {
        const { label, href } = parseDocLink(doc)
        return (
          <li key={i}>
            {href ? (
              <>
                <a href={href} target="_blank" rel="noopener noreferrer" className="nb-doc-link">
                  {label}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
                <span className="nb-doc-host">{hostOf(href)}</span>
              </>
            ) : (
              <span className="nb-doc-plain">{label}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
