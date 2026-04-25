type ProductBadgeProps = { tag: string }

export function ProductBadge({ tag }: ProductBadgeProps) {
  if (!tag) return null
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '11px',
        fontWeight: 500,
        color: 'var(--accent)',
        backgroundColor: 'var(--accent-subtle)',
        border: '1px solid var(--accent)',
        borderRadius: '4px',
        padding: '2px 8px',
        letterSpacing: '0.02em',
      }}
    >
      {tag}
    </span>
  )
}
