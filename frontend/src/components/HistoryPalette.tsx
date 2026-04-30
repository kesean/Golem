import { useEffect } from 'react'
import { SignInButton } from '@clerk/clerk-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command'
import { useHistory } from '../hooks/useHistory'
import type { HistoryEntry } from '../hooks/useHistory'

type HistoryPaletteProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (entry: HistoryEntry) => void
  isGuest?: boolean
}

export function HistoryPalette({ open, onOpenChange, onSelect, isGuest }: HistoryPaletteProps) {
  const { entries } = useHistory(isGuest)

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        onOpenChange(true)
      }
    }
    window.addEventListener('keydown', handleKeydown)
    return () => window.removeEventListener('keydown', handleKeydown)
  }, [onOpenChange])

  if (isGuest) {
    if (!open) return null
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="History unavailable"
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
        }}
        onClick={() => onOpenChange(false)}
      >
        <div
          style={{
            backgroundColor: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            padding: '32px',
            maxWidth: '400px',
            width: '90%',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
          onClick={e => e.stopPropagation()}
        >
          <p
            style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '15px',
              color: 'var(--text)',
              margin: 0,
            }}
          >
            Chat history requires an account. Sign in to save your conversations.
          </p>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button
              onClick={() => onOpenChange(false)}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                backgroundColor: 'transparent',
                color: 'var(--text-secondary)',
                fontFamily: "'DM Sans', sans-serif",
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              Close
            </button>
            <SignInButton mode="modal">
              <button
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: 'var(--accent)',
                  color: '#fff',
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: '14px',
                  cursor: 'pointer',
                }}
              >
                Sign in
              </button>
            </SignInButton>
          </div>
        </div>
      </div>
    )
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search history…" />
      <CommandList>
        <CommandEmpty>No history yet.</CommandEmpty>
        <CommandGroup heading="Recent Questions">
          {entries.map(entry => (
            <CommandItem
              key={entry._id}
              onSelect={() => {
                onSelect(entry)
                onOpenChange(false)
              }}
              style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '14px' }}
            >
              {entry.question}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
