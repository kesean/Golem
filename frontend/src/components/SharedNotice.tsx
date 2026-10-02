import { Button } from './ui/button'
import type { SharedView } from '../hooks/useSharedEntry'

type SharedNoticeProps = { view: SharedView; onAskOwn: () => void }

const COPY: Record<Exclude<SharedView, 'none'>, string> = {
  found: "Shared by another user. It wasn't generated for you and may have been edited.",
  notFound: "This shared link doesn't work. The answer may have been deleted.",
}

/**
 * Always mounted (empty when there's nothing to say) so screen readers
 * announce the notice when it appears. Deliberately plain text rather than a
 * badge: the answer below can be authored by another user and must not be
 * able to imitate it.
 */
export function SharedNotice({ view, onAskOwn }: SharedNoticeProps) {
  return (
    <div role="status">
      {view !== 'none' && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px 12px',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            margin: '12px 0',
          }}
        >
          <p
            style={{
              margin: 0,
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '13px',
              color: 'var(--text-secondary)',
            }}
          >
            {COPY[view]}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={onAskOwn}
            style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '12px' }}
          >
            Ask your own question
          </Button>
        </div>
      )}
    </div>
  )
}
