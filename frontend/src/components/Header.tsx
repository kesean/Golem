import type { Theme } from '../hooks/useTheme'

type HeaderProps = {
  theme: Theme
  onToggleTheme: () => void
  onOpenHistory: () => void
  onNewConversation: () => void
  userName?: string
}

export function Header({
  theme,
  onToggleTheme,
  onOpenHistory,
  onNewConversation,
  userName,
}: HeaderProps) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 24px',
        borderBottom: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg)',
      }}
    >
      <span
        style={{
          fontFamily: "'Newsreader', serif",
          fontSize: '18px',
          fontWeight: 600,
          color: 'var(--accent)',
        }}
      >
        Dev Support AI
      </span>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          onClick={onNewConversation}
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '13px',
            color: 'var(--text-secondary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '6px 10px',
          }}
        >
          New conversation
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
            padding: '5px 10px',
          }}
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
            padding: '5px 10px',
            color: 'var(--text-secondary)',
            fontSize: '14px',
          }}
        >
          {theme === 'light' ? '🌙' : '☀️'}
        </button>

        {userName && (
          <span
            style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '12px',
              color: 'var(--text-muted)',
              marginLeft: '4px',
            }}
          >
            {userName}
          </span>
        )}
      </div>
    </header>
  )
}
