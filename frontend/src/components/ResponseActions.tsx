import { useState } from 'react'
import { Button } from './ui/button'
import type { ParsedResponse } from '../types'

type ResponseActionsProps = {
  parsedResponse: ParsedResponse
  historyId: string | null
}

export function ResponseActions({ parsedResponse, historyId }: ResponseActionsProps) {
  const [copyLabel, setCopyLabel] = useState('Copy')
  const [shareLabel, setShareLabel] = useState('Share')

  function handleCopy() {
    const parts: string[] = []
    if (parsedResponse.summary) parts.push(`Summary\n${parsedResponse.summary}`)
    if (parsedResponse.rootCause) parts.push(`Root Cause\n${parsedResponse.rootCause}`)
    if (parsedResponse.debugSteps.length) {
      parts.push(`Debug Steps\n${parsedResponse.debugSteps.join('\n')}`)
    }
    if (parsedResponse.docs.length) {
      parts.push(`Docs\n${parsedResponse.docs.join('\n')}`)
    }
    navigator.clipboard.writeText(parts.join('\n\n')).then(() => {
      setCopyLabel('Copied!')
      setTimeout(() => setCopyLabel('Copy'), 2000)
    })
  }

  function handleShare() {
    if (!historyId) return
    const url = `${window.location.origin}${window.location.pathname}?share=${historyId}`
    navigator.clipboard.writeText(url).then(() => {
      setShareLabel('Copied link!')
      setTimeout(() => setShareLabel('Share'), 2000)
    })
  }

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <Button
        variant="outline"
        size="sm"
        onClick={handleCopy}
        style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '12px' }}
      >
        {copyLabel}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleShare}
        disabled={!historyId}
        style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '12px' }}
      >
        {shareLabel}
      </Button>
    </div>
  )
}
