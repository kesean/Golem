import { useState, useEffect } from 'react'
import { Skeleton } from './ui/skeleton'
import { ProductBadge } from './ProductBadge'
import { NotebookRow, MarkdownContent, StepList, DocList } from './SectionCard'
import { FeedbackButtons } from './FeedbackButtons'
import { ResponseActions } from './ResponseActions'
import { DebugPanel } from './DebugPanel'
import type { ParsedResponse, RetrievedChunk } from '../types'

function ThinkingIndicator() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
        {[0, 1, 2].map(i => (
          <span key={i} className="thinking-dot" style={{ animationDelay: `${i * 0.16}s` }} />
        ))}
      </div>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '13px', color: 'var(--text-secondary)' }}>
        Analyzing your question…
      </span>
    </div>
  )
}

type ResponsePanelProps = {
  isLoading: boolean
  isStreaming: boolean
  parsedResponse: ParsedResponse | null
  error: string | null
  evalId: string | null
  historyId: string | null
  chunks: RetrievedChunk[]
}

export function ResponsePanel({
  isLoading,
  isStreaming,
  parsedResponse,
  error,
  evalId,
  historyId,
  chunks,
}: ResponsePanelProps) {
  const [showWarmup, setShowWarmup] = useState(false)

  useEffect(() => {
    if (!isLoading) {
      setShowWarmup(false)
      return
    }
    const timer = setTimeout(() => setShowWarmup(true), 2000)
    return () => clearTimeout(timer)
  }, [isLoading])

  // Mounted before any content so screen readers announce changes to it.
  // Streamed sections are deliberately not live: they would be read out token by token.
  const status = error
    ? ''
    : isLoading
      ? 'Analyzing your question.'
      : parsedResponse
        ? 'Answer ready.'
        : ''

  return (
    <>
      <div role="status" aria-live="polite" className="sr-only">
        {status}
      </div>
      <ResponseBody
        isLoading={isLoading}
        isStreaming={isStreaming}
        parsedResponse={parsedResponse}
        error={error}
        evalId={evalId}
        historyId={historyId}
        chunks={chunks}
        showWarmup={showWarmup}
      />
    </>
  )
}

function ResponseBody({
  isLoading,
  isStreaming,
  parsedResponse,
  error,
  evalId,
  historyId,
  chunks,
  showWarmup,
}: ResponsePanelProps & { showWarmup: boolean }) {
  if (!isLoading && !parsedResponse && !error) return null

  // Show the skeleton only before the first content arrives — once deltas
  // start streaming in, parsedResponse is set and we fall through to render
  // sections live instead of waiting for isLoading to become false.
  if (isLoading && !parsedResponse) {
    return (
      <div
        id="skeleton"
        aria-hidden="true"
        style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}
      >
        <ThinkingIndicator />
        {showWarmup && (
          <span
            style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '12px',
              color: 'var(--text-secondary)',
            }}
          >
            This may take a few seconds — the server is warming up.
          </span>
        )}
        <Skeleton style={{ height: '20px', width: '30%' }} />
        <Skeleton style={{ height: '80px' }} />
        <Skeleton style={{ height: '60px' }} />
        <Skeleton style={{ height: '100px' }} />
      </div>
    )
  }

  if (error) {
    return (
      <div
        id="response-area"
        role="alert"
        aria-live="assertive"
        style={{
          padding: '24px',
          color: 'var(--text-secondary)',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '14px',
        }}
      >
        {error}
      </div>
    )
  }

  if (!parsedResponse) return null

  return (
    <div
      id="response-area"
      role="region"
      aria-label="Response"
      className="nb-doc"
      style={{ padding: '24px' }}
    >
      {parsedResponse.productTag && (
        <ProductBadge tag={parsedResponse.productTag} />
      )}

      <div className="nb-summary">
        <MarkdownContent content={parsedResponse.summary} />
      </div>

      <NotebookRow label="Cause" marked>
        <MarkdownContent content={parsedResponse.rootCause} />
      </NotebookRow>

      {parsedResponse.debugSteps.length > 0 && (
        <NotebookRow label="Fix">
          <StepList steps={parsedResponse.debugSteps} />
        </NotebookRow>
      )}

      {parsedResponse.docs.length > 0 && (
        <NotebookRow label="Docs">
          <DocList docs={parsedResponse.docs} />
        </NotebookRow>
      )}

      {!isStreaming && <DebugPanel chunks={chunks} />}

      {!isStreaming && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '4px',
          }}
        >
          <FeedbackButtons evalId={evalId} />
          <ResponseActions parsedResponse={parsedResponse} historyId={historyId} />
        </div>
      )}
    </div>
  )
}
