import React from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

type SectionCardProps = {
  title: string
  accentColor: string
  children: React.ReactNode
  animationDelay?: number
}

export function SectionCard({ title, accentColor, children, animationDelay = 0 }: SectionCardProps) {
  return (
    <div
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${accentColor}`,
        borderRadius: '10px',
        padding: '20px 24px',
        animationDelay: `${animationDelay}ms`,
      }}
    >
      <h3
        style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase' as const,
          color: accentColor,
          margin: '0 0 12px',
        }}
      >
        {title}
      </h3>
      <div
        style={{
          fontFamily: "'Newsreader', serif",
          fontSize: '16px',
          lineHeight: 1.7,
          color: 'var(--text-primary)',
        }}
      >
        {children}
      </div>
    </div>
  )
}

function safeHtml(markdown: string): string {
  return DOMPurify.sanitize(marked.parse(markdown) as string)
}

export function MarkdownContent({ content }: { content: string }) {
  return <div dangerouslySetInnerHTML={{ __html: safeHtml(content) }} />
}

export function StepList({ steps }: { steps: string[] }) {
  return (
    <ol style={{ paddingLeft: '20px', margin: 0 }}>
      {steps.map((step, i) => (
        <li
          key={i}
          style={{ marginBottom: '4px' }}
          dangerouslySetInnerHTML={{ __html: safeHtml(step) }}
        />
      ))}
    </ol>
  )
}

export function DocList({ docs }: { docs: string[] }) {
  return (
    <ul style={{ paddingLeft: '20px', margin: 0 }}>
      {docs.map((doc, i) => (
        <li key={i} style={{ marginBottom: '4px' }}>
          <a
            href={doc}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '13px',
              color: 'var(--col-docs)',
              textDecoration: 'none',
            }}
          >
            {doc}
          </a>
        </li>
      ))}
    </ul>
  )
}
