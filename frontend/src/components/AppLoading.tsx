// Shown while auth or the guest session loads, so the page is never blank.
export function AppLoading() {
  return (
    <div
      role="status"
      style={{
        minHeight: '100dvh',
        backgroundColor: 'var(--bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '10px',
      }}
    >
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
  )
}
