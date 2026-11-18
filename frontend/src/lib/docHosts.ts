// Hosts a doc link may point at. Mirrors the retrieval sources (retrieval.py):
// Clerk docs under clerk.com (including its subdomains) and MDN under
// developer.mozilla.org. Anything else is shown as plain text.
const EXACT_HOSTS = ['clerk.com', 'developer.mozilla.org']
const HOST_SUFFIXES = ['.clerk.com']

/**
 * True only for an https URL with no userinfo or port whose parsed hostname is
 * an allowed host. Compares the parsed hostname, never a substring, so
 * look-alikes such as clerk.com.evil.test or evilclerk.com fail, and so does
 * a userinfo trick such as https://clerk.com@evil.test.
 */
export function isAllowedDocHref(href: string): boolean {
  let url: URL
  try {
    url = new URL(href)
  } catch {
    return false
  }
  if (url.protocol !== 'https:') return false
  if (url.username || url.password || url.port) return false
  const host = url.hostname
  return EXACT_HOSTS.includes(host) || HOST_SUFFIXES.some((suffix) => host.endsWith(suffix))
}
