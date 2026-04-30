import { useState, useEffect } from 'react'
import { Skeleton } from './ui/skeleton'
import { ProductBadge } from './ProductBadge'
import { SectionCard, MarkdownContent, StepList, DocList } from './SectionCard'
import { FeedbackButtons } from './FeedbackButtons'
import { ResponseActions } from './ResponseActions'
import type { ParsedResponse } from '../types'

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
  parsedResponse: ParsedResponse | null
  error: string | null
  evalId: string | null
  historyId: string | null
}

export function ResponsePanel({
  isLoading,
  parsedResponse,
  error,
  evalId,
  historyId,
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

  if (!isLoading && !parsedResponse && !error) return null

  if (isLoading) {
    return (
      <div
        id="skeleton"
        role="status"
        aria-live="polite"
        aria-label="Loading response"
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
      style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      {parsedResponse.productTag && (
        <ProductBadge tag={parsedResponse.productTag} />
      )}

      <SectionCard title="Summary" accentColor="var(--accent)" animationDelay={0}>
        <MarkdownContent content={parsedResponse.summary} />
      </SectionCard>

      <SectionCard title="Root Cause" accentColor="var(--col-root)" animationDelay={80}>
        <MarkdownContent content={parsedResponse.rootCause} />
      </SectionCard>

      {parsedResponse.debugSteps.length > 0 && (
        <SectionCard title="Debug Steps" accentColor="var(--col-steps)" animationDelay={160}>
          <StepList steps={parsedResponse.debugSteps} />
        </SectionCard>
      )}

      {parsedResponse.docs.length > 0 && (
        <SectionCard title="Documentation" accentColor="var(--col-docs)" animationDelay={240}>
          <DocList docs={parsedResponse.docs} />
        </SectionCard>
      )}

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
    </div>
  )
}
