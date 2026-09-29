type ProductBadgeProps = { tag: string }

export function ProductBadge({ tag }: ProductBadgeProps) {
  if (!tag) return null
  return (
    <span className="nb-tag">
      <span className="nb-tag-dot" aria-hidden="true" />
      {tag}
    </span>
  )
}
