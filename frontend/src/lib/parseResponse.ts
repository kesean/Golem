import type { ParsedResponse } from '../types'

function parseSection(xml: string, tag: string): string {
  const open = xml.indexOf(`<${tag}>`)
  if (open === -1) return ''
  const start = open + tag.length + 2
  const close = xml.indexOf(`</${tag}>`, start)
  return (close === -1 ? xml.slice(start) : xml.slice(start, close)).trim()
}

function parseLines(text: string): string[] {
  return text.split('\n').map(s => s.trim()).filter(Boolean)
}

export function parseResponse(xml: string): ParsedResponse {
  return {
    productTag: parseSection(xml, 'product_tag'),
    summary: parseSection(xml, 'summary'),
    rootCause: parseSection(xml, 'root_cause'),
    debugSteps: parseLines(parseSection(xml, 'debug_steps')),
    docs: parseLines(parseSection(xml, 'docs')),
  }
}
