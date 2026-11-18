import { useEffect, useState } from 'react'
import { Button } from './ui/button'

// After this long, assume Clerk or the network is stuck and offer a way out
export const STILL_LOADING_MS = 8000

// Shown while auth or the guest session loads, so the page is never blank.
export function AppLoading() {
  const [stuck, setStuck] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setStuck(true), STILL_LOADING_MS)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div
      role="status"
      style={{
        minHeight: '100dvh',
        backgroundColor: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '16px',
        padding: '24px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div aria-hidden="true" style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <span key={i} className="thinking-dot" style={{ animationDelay: `${i * 0.16}s` }} />
          ))}
        </div>
        <span
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '13px',
            color: 'var(--text-secondary)',
          }}
        >
          Loading…
        </span>
      </div>
      {stuck && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
          <p
            style={{
              margin: 0,
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '14px',
              color: 'var(--text-secondary)',
              textAlign: 'center',
            }}
          >
            Still loading. Check your connection or reload.
          </p>
          <Button
            className="min-h-11"
            variant="outline"
            onClick={() => window.location.reload()}
            style={{
              borderColor: 'var(--border-strong)',
              color: 'var(--text-primary)',
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            Reload
          </Button>
        </div>
      )}
    </div>
  )
}
