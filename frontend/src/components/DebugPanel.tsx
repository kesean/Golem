import { useState } from 'react'
import type { RetrievedChunk } from '../types'

type DebugPanelProps = {
  chunks: RetrievedChunk[]
}

/**
 * Collapsible panel showing the RAG chunks retrieved for the current
 * response — what was actually injected into the prompt, for debugging
 * retrieval quality. Renders nothing when RAG found no matches.
 */
export function DebugPanel({ chunks }: DebugPanelProps) {
  const [open, setOpen] = useState(false)

  if (chunks.length === 0) return null

  return (
    <div
      id="debug-panel"
      style={{
        border: '1px solid var(--border-color)',
        borderRadius: '10px',
        overflow: 'hidden',
      }}
    >
      <button
        id="debug-panel-toggle"
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '12px',
          fontWeight: 600,
          letterSpacing: '0.04em',
          color: 'var(--text-secondary)',
        }}
      >
        <span>{open ? '▾' : '▸'} Retrieved docs ({chunks.length})</span>
      </button>

      {open && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            padding: '0 16px 16px',
          }}
        >
          {chunks.map((chunk, i) => (
            <div
              key={i}
              style={{
                borderLeft: '3px solid var(--col-docs)',
                paddingLeft: '12px',
              }}
            >
              <div
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '11px',
                  color: 'var(--col-docs)',
                  marginBottom: '4px',
                }}
              >
                [{chunk.source}] {chunk.path}
              </div>
              <div
                style={{
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: '13px',
                  lineHeight: 1.6,
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {chunk.text}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
