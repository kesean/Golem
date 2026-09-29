export type DocLink = { label: string; href: string | null }

/**
 * Validate and extract URL components, rejecting non-http(s) schemes and userinfo
 */
function validateUrl(candidate: string): { valid: boolean; href: string | null } {
  try {
    const url = new URL(candidate)
    if (!['http:', 'https:'].includes(url.protocol)) {
      return { valid: false, href: null }
    }
    if (url.username || url.password) {
      return { valid: false, href: null }
    }
    return { valid: true, href: candidate }
  } catch {
    return { valid: false, href: null }
  }
}

/**
 * Strip trailing punctuation while respecting balanced parentheses.
 * Removes trailing ')' only if count of ')' > count of '('.
 * Also removes trailing ASCII and unicode punctuation (. , ; : ! ? ' " » etc.)
 * Loops until stable: keeps running until the string stops changing.
 */
function stripTrailingPunctuation(url: string): string {
  let result = url
  let previousResult: string

  // Loop until stable: keep running the cleanup until the result doesn't change
  do {
    previousResult = result

    // Handle unbalanced closing parentheses
    while (result.endsWith(')')) {
      const openCount = (result.match(/\(/g) || []).length
      const closeCount = (result.match(/\)/g) || []).length
      if (closeCount > openCount) {
        result = result.slice(0, -1)
      } else {
        break
      }
    }

    // Strip trailing punctuation (ASCII and unicode)
    // Includes: . , ; : ! ? ' " « » … ` and * (backticks and asterisks)
    // Excludes ( and ) since they're handled by balanced parens logic above
    result = result.replace(/[.,;:!?'"«»……`*]+$/, '')
  } while (result !== previousResult)

  return result
}

/**
 * Extract URL from text, handling angle brackets, backticks, and asterisks
 */
function extractUrl(text: string): { url: string; beforeUrl: string } | null {
  // Try angle-bracket format first: <URL>
  const angleBracketMatch = text.match(/^(.*?)<(https?:\/\/[^>]+)>/i)
  if (angleBracketMatch) {
    return {
      url: angleBracketMatch[2],
      beforeUrl: angleBracketMatch[1],
    }
  }

  // Try regular URL pattern (excluding backticks and asterisks from URL chars)
  // URL can include balanced parens, but not whitespace, <, >, quotes, backticks, or asterisks
  const urlMatch = text.match(/https?:\/\/[^\s<>"`*]+/i)
  if (urlMatch) {
    return {
      url: urlMatch[0],
      beforeUrl: text.slice(0, urlMatch.index),
    }
  }

  return null
}

/**
 * Clean label by removing list markers and markdown emphasis
 */
function cleanLabel(label: string): string {
  let result = label.trim()

  // Strip leading list markers: "- ", "* ", "1. ", "1) "
  result = result.replace(/^[\d]*[.\)]\s+/, '').replace(/^[-*]\s+/, '')

  // Strip surrounding markdown emphasis
  // Handle **, *, _, and backticks
  result = result.replace(/^(\*\*|__|`)(.*)\1$/, '$2')
  result = result.replace(/^(_|\*)(.*)\1$/, '$2')

  // Strip angle brackets from edges
  result = result.replace(/^<+/, '').replace(/>+$/, '')

  return result.trim()
}

export function parseDocLink(raw: string): DocLink {
  const text = raw.trim()

  // Try markdown link format first: [label](url)
  const markdownMatch = text.match(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/i)
  if (markdownMatch) {
    const mdLabel = markdownMatch[1]
    const mdHref = markdownMatch[2]
    const validation = validateUrl(mdHref)
    return {
      label: cleanLabel(mdLabel),
      href: validation.href,
    }
  }

  // Extract URL (handles both angle-bracket and regular formats)
  const urlData = extractUrl(text)
  if (!urlData) {
    return { label: text, href: null }
  }

  let { url, beforeUrl } = urlData

  // Strip trailing punctuation while respecting balanced parens
  url = stripTrailingPunctuation(url)

  // Validate URL
  const validation = validateUrl(url)
  if (!validation.href) {
    return { label: text, href: null }
  }

  // Extract and clean label from text before URL
  let label = beforeUrl.trim()

  // Clean up list markers and markdown emphasis
  label = cleanLabel(label)

  // Remove trailing separators and angle brackets (but not backticks or asterisks yet)
  label = label.replace(/[\s:(\-–—<>]+$/, '').trim()

  // Remove trailing asterisks and backticks only if they don't form balanced pairs
  // (e.g., remove trailing backticks from "See `" but keep them in "*Title*" or "**Title**")
  let previousLabel: string
  do {
    previousLabel = label
    while (label.endsWith('*') || label.endsWith('`')) {
      const match = label.match(/^(\*\*|\_\_|`|\*|\_)(.*)\1$/)
      if (match) {
        // It's a balanced pair, stop stripping
        break
      }
      // Not balanced, remove the trailing character
      label = label.slice(0, -1).trim()
    }
    // After removing trailing punctuation, strip any remaining trailing separators
    label = label.replace(/[\s:(\-–—<>]+$/, '').trim()
  } while (label !== previousLabel)

  // Apply cleanLabel again to handle cases where the separators exposed the markup delimiters
  label = cleanLabel(label)

  // If label is empty or just markup, use the URL as the label
  if (!label || label === '`' || label === '*' || label === '**') {
    label = url
  }

  return {
    label,
    href: validation.href,
  }
}
