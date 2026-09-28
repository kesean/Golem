export type AskEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; response: string; input_tokens: number; output_tokens: number; latency_ms: number }
  | { type: 'error'; error: string }

/**
 * Parse Server-Sent Events frames out of a raw SSE chunk buffer.
 *
 * Frames are separated by a blank line ("\n\n"). Returns the parsed events
 * found in `buffer` and whatever trailing partial frame should be kept for
 * the next chunk. Non-"data:" lines and blank/unparsable frames are skipped.
 */
export function parseSSEChunk(buffer: string): { events: AskEvent[]; rest: string } {
  const frames = buffer.split('\n\n')
  const rest = frames.pop() ?? ''
  const events: AskEvent[] = []

  for (const frame of frames) {
    const line = frame.trim()
    if (!line.startsWith('data: ')) continue
    try {
      events.push(JSON.parse(line.slice('data: '.length)) as AskEvent)
    } catch {
      // malformed frame — skip it rather than crash the stream
    }
  }

  return { events, rest }
}
