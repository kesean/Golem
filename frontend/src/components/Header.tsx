import { useState } from 'react'
import { useQuery } from 'convex/react'
import { api } from '../../convex/_generated/api'
import { CircleHelp } from 'lucide-react'
import type { Theme } from '../hooks/useTheme'

type HeaderProps = {
  theme: Theme
  onToggleTheme: () => void
  onOpenHistory: () => void
  onOpenTour: () => void
  onNewConversation: () => void
  userName?: string
  onSignOut?: () => void
}

export function Header({
  theme,
  onToggleTheme,
  onOpenHistory,
  onOpenTour,
  onNewConversation,
  userName,
  onSignOut,
}: HeaderProps) {
  const [signOutHovered, setSignOutHovered] = useState(false)
  const totalQuestions = useQuery(api.stats.getGlobalCount)

  // Compute counter label once
  const counterLabel =
    totalQuestions !== undefined
      ? `${totalQuestions.toLocaleString()} ${totalQuestions === 1 ? 'question' : 'questions'} answered`
      : ''
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 12px',
        borderBottom: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg)',
        flexWrap: 'nowrap',
        gap: '8px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'nowrap', minWidth: 0 }}>
        <h1
          style={{
            fontFamily: "'Newsreader', serif",
            fontSize: '18px',
            fontWeight: 600,
            color: 'var(--accent)',
            margin: 0,
          }}
        >
          Golem
        </h1>
        {totalQuestions !== undefined && (
          <>
            <span
              className="hidden sm:inline"
              style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: '12px',
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
              }}
            >
              · {totalQuestions.toLocaleString()} {totalQuestions === 1 ? 'question' : 'questions'} answered
            </span>
            <span
              className="sm:hidden"
              style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: '12px',
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
              }}
              aria-hidden="true"
            >
              · {totalQuestions.toLocaleString()}
            </span>
            <span className="sr-only">{counterLabel}</span>
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'nowrap', minWidth: 0 }}>
        <button
          onClick={onNewConversation}
          aria-label="New conversation"
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '13px',
            color: 'var(--text-secondary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            minHeight: '44px',
            minWidth: '44px',
            whiteSpace: 'nowrap',
          }}
          className="px-1 sm:px-2.5"
        >
          <span className="hidden sm:inline">New conversation</span>
          <span className="sm:hidden">New</span>
        </button>

        <button
          onClick={onOpenHistory}
          aria-label="Open history (Ctrl+K)"
          title="Ctrl+K"
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '13px',
            color: 'var(--text-secondary)',
            background: 'none',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            cursor: 'pointer',
            minHeight: '44px',
            minWidth: '44px',
            whiteSpace: 'nowrap',
          }}
          className="px-1.5 sm:px-2.5"
        >
          History
        </button>

        <button
          onClick={onToggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          aria-pressed={theme === 'dark'}
          style={{
            background: 'none',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            cursor: 'pointer',
            minHeight: '44px',
            minWidth: '44px',
            color: 'var(--text-secondary)',
            fontSize: '14px',
            whiteSpace: 'nowrap',
          }}
          className="px-1.5 sm:px-2.5"
        >
          {theme === 'light' ? '🌙' : '☀️'}
        </button>

        <button
          id="tour-btn"
          onClick={onOpenTour}
          aria-label="Show guided tour"
          title="Show guided tour"
          style={{
            background: 'none',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            cursor: 'pointer',
            minHeight: '44px',
            minWidth: '44px',
            color: 'var(--text-secondary)',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
          className="px-1.5 sm:px-2.5"
        >
          <CircleHelp size={16} strokeWidth={2} />
        </button>

        {userName && (
          <span
            className="hidden sm:inline"
            style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '12px',
              color: 'var(--text-muted)',
              marginLeft: '4px',
              whiteSpace: 'nowrap',
            }}
          >
            {userName}
          </span>
        )}

        {onSignOut && (
          <button
            onClick={onSignOut}
            onMouseEnter={() => setSignOutHovered(true)}
            onMouseLeave={() => setSignOutHovered(false)}
            aria-label="Sign out"
            style={{
              display: 'flex',
              alignItems: 'center',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '13px',
              color: signOutHovered ? '#a85238' : 'var(--text-secondary)',
              background: 'none',
              border: `1px solid ${signOutHovered ? '#a85238' : 'var(--border-color)'}`,
              borderRadius: '6px',
              cursor: 'pointer',
              paddingTop: '5px',
              paddingBottom: '5px',
              transition: 'color 0.15s ease, border-color 0.15s ease',
              marginLeft: '4px',
              whiteSpace: 'nowrap',
            }}
            className="px-1.5 sm:px-2.5 sm:gap-1.5"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 13 13"
              fill="none"
              aria-hidden="true"
              style={{
                transform: signOutHovered ? 'translateX(1px)' : 'translateX(0)',
                transition: 'transform 0.15s ease',
                flexShrink: 0,
              }}
            >
              <path
                d="M5 2H2.5C2.22 2 2 2.22 2 2.5v8c0 .28.22.5.5.5H5"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
              />
              <path
                d="M8.5 9L11 6.5 8.5 4"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <line
                x1="4.5"
                y1="6.5"
                x2="11"
                y2="6.5"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
              />
            </svg>
            <span className="hidden sm:inline">Sign out</span>
          </button>
        )}
      </div>
    </header>
  )
}
