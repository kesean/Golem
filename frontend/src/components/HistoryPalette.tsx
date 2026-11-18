import { useEffect, useId } from 'react'
import { SignInButton } from '@clerk/clerk-react'
import { useCommandState } from 'cmdk'
import {
  CommandDialog,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { Button } from './ui/button'
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
    // Same focus trap, Escape and focus return as TourDialog, from ui/dialog.
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          showCloseButton={false}
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            maxWidth: '400px',
            width: '90%',
          }}
        >
          <DialogHeader>
            <DialogTitle style={{ color: 'var(--text-primary)' }}>History unavailable</DialogTitle>
            <DialogDescription style={{ color: 'var(--text-secondary)' }}>
              Chat history requires an account. Sign in to save your conversations.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose
              render={
                <Button
                  variant="outline"
                  className="min-h-11"
                  style={{ borderColor: 'var(--border-strong)', color: 'var(--text-secondary)' }}
                />
              }
            >
              Close
            </DialogClose>
            <SignInButton mode="modal">
              <Button
                className="min-h-11"
                style={{ backgroundColor: 'var(--accent)', color: 'var(--btn-text)' }}
              >
                Sign in
              </Button>
            </SignInButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Question history"
      description="Search your past questions"
    >
      <HistoryPaletteBody entries={entries} onSelect={onSelect} onOpenChange={onOpenChange} />
    </CommandDialog>
  )
}

// Rendered inside cmdk's <Command> (via CommandDialog) so useCommandState works.
function HistoryPaletteBody({
  entries,
  onSelect,
  onOpenChange,
}: {
  entries: HistoryEntry[]
  onSelect: (entry: HistoryEntry) => void
  onOpenChange: (open: boolean) => void
}) {
  // True both when there is no history and when the search matches nothing.
  const noResults = useCommandState(state => state.filtered.count === 0)
  const emptyMessage = entries.length === 0 ? 'No history yet.' : 'No matching questions.'
  const messageId = useId()

  return (
    <>
      {/* The input is focused when the dialog opens, and a live region that
          mounts with the dialog is not announced, so the message is also the
          input's description. The wrapper always exists, so the reference is
          always valid; it is empty (no description) while there are results.
          cmdk labels the input with an empty <label>, so it needs aria-label. */}
      <CommandInput
        placeholder="Search history…"
        aria-label="Search history"
        aria-describedby={messageId}
      />
      {/* Outside the listbox: an empty cmdk listbox fails aria-required-children,
          so the list is aria-hidden while empty and this polite live region
          announces the message when a search stops matching. cmdk points the
          input's aria-controls at the list, so the list must stay mounted. */}
      <div id={messageId} aria-live="polite">
        {noResults && <p className="py-6 text-center text-sm">{emptyMessage}</p>}
      </div>
      <CommandList aria-hidden={noResults}>
        {entries.length > 0 && (
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
        )}
      </CommandList>
    </>
  )
}
