import { describe, it, expect } from 'vitest'
import { parseResponse } from '../src/lib/parseResponse'

const SAMPLE_XML = `<product_tag>Authentication</product_tag>
<summary>
This is a test summary.
</summary>
<root_cause>
The root cause is missing credentials.
</root_cause>
<debug_steps>
Step 1: Check your API key
Step 2: Verify the header format
</debug_steps>
<docs>
https://docs.example.com/auth
</docs>`

describe('parseResponse', () => {
  it('extracts productTag', () => {
    expect(parseResponse(SAMPLE_XML).productTag).toBe('Authentication')
  })

  it('extracts summary trimmed', () => {
    expect(parseResponse(SAMPLE_XML).summary).toBe('This is a test summary.')
  })

  it('extracts rootCause trimmed', () => {
    expect(parseResponse(SAMPLE_XML).rootCause).toBe('The root cause is missing credentials.')
  })

  it('extracts debugSteps as array', () => {
    expect(parseResponse(SAMPLE_XML).debugSteps).toEqual([
      'Step 1: Check your API key',
      'Step 2: Verify the header format',
    ])
  })

  it('extracts docs as array', () => {
    expect(parseResponse(SAMPLE_XML).docs).toEqual([
      'https://docs.example.com/auth',
    ])
  })

  it('returns empty string for absent productTag', () => {
    const xml = '<summary>test</summary><root_cause>x</root_cause><debug_steps>Step 1: x</debug_steps><docs></docs>'
    expect(parseResponse(xml).productTag).toBe('')
  })

  it('returns empty array when docs section is empty', () => {
    const xml = '<product_tag>X</product_tag><summary>s</summary><root_cause>r</root_cause><debug_steps>Step 1: x</debug_steps><docs></docs>'
    expect(parseResponse(xml).docs).toEqual([])
  })

  it('handles missing closing tag in summary', () => {
    expect(parseResponse('<summary>partial content').summary).toBe('partial content')
  })
})
