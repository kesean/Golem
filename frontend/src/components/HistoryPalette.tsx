import { useEffect } from 'react'
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
}

export function HistoryPalette({ open, onOpenChange, onSelect }: HistoryPaletteProps) {
  const { entries } = useHistory()

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
