/**
 * app.test.js — Unit tests for frontend/src/app.js
 *
 * We mock the Convex generated API because app.js imports it at module load
 * time; the generated file assumes a live Convex deployment.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock Convex generated API before importing app.js
vi.mock('../convex/_generated/api.js', () => ({
  api: {
    history: {
      list: 'history:list',
      add: 'history:add',
      clear: 'history:clear',
      getById: 'history:getById',
    },
  },
}))

import {
  extractSection,
  renderResponse,
  newConversation,
  copyResponse,
  shareResponse,
} from '../src/app.js'

// ── Full DOM fixture used by all tests ────────────────────────────────────────

const DOM_HTML = `
  <span   id="product-tag-badge" class="hidden"></span>
  <div    id="summary"></div>
  <div    id="root-cause"></div>
  <ol     id="debug-steps"></ol>
  <div    id="docs-section" class="hidden">
    <ul   id="docs"></ul>
  </div>
  <div    id="response-area" class="hidden"></div>
  <div    id="error-area"    class="hidden"></div>
  <button id="share-btn">Share</button>
  <button id="copy-btn">Copy</button>
  <textarea id="question"></textarea>
  <ul     id="history-list"></ul>
`

beforeEach(() => {
  document.body.innerHTML = DOM_HTML
  vi.clearAllMocks()
})

// ── extractSection ────────────────────────────────────────────────────────────

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

describe('extractSection', () => {
  it('extracts content from a known tag', () => {
    const result = extractSection(SAMPLE_XML, 'summary')
    expect(result).not.toBeNull()
    expect(result.content).toBe('This is a test summary.')
    expect(result.closed).toBe(true)
  })

  it('returns null when the tag is absent', () => {
    expect(extractSection('<foo>bar</foo>', 'missing')).toBeNull()
  })

  it('handles a missing closing tag gracefully', () => {
    const result = extractSection('<summary>partial content', 'summary')
    expect(result.content).toBe('partial content')
    expect(result.closed).toBe(false)
  })

  it('extracts product_tag content', () => {
    const result = extractSection(SAMPLE_XML, 'product_tag')
    expect(result.content).toBe('Authentication')
  })
})

// ── renderResponse ────────────────────────────────────────────────────────────

describe('renderResponse', () => {
  it('populates #summary with parsed content', () => {
    renderResponse(SAMPLE_XML)
    expect(document.getElementById('summary').innerHTML).toContain('This is a test summary.')
  })

  it('populates #root-cause with parsed content', () => {
    renderResponse(SAMPLE_XML)
    expect(document.getElementById('root-cause').innerHTML).toContain('The root cause is missing credentials.')
  })

  it('renders debug steps as list items', () => {
    renderResponse(SAMPLE_XML)
    const items = document.getElementById('debug-steps').querySelectorAll('li')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toContain('Check your API key')
    expect(items[1].textContent).toContain('Verify the header format')
  })

  it('adds .sections-ready class to #response-area', () => {
    renderResponse(SAMPLE_XML)
    expect(document.getElementById('response-area').classList.contains('sections-ready')).toBe(true)
  })

  it('removes .hidden from #response-area', () => {
    renderResponse(SAMPLE_XML)
    expect(document.getElementById('response-area').classList.contains('hidden')).toBe(false)
  })

  it('shows product-tag-badge when tag is present', () => {
    renderResponse(SAMPLE_XML)
    const badge = document.getElementById('product-tag-badge')
    expect(badge.textContent).toBe('Authentication')
    expect(badge.classList.contains('hidden')).toBe(false)
  })

  it('hides product-tag-badge when product_tag is absent', () => {
    const xmlNoTag = `<summary>test</summary><root_cause>x</root_cause><debug_steps>Step 1: x</debug_steps><docs></docs>`
    renderResponse(xmlNoTag)
    expect(document.getElementById('product-tag-badge').classList.contains('hidden')).toBe(true)
  })

  it('shows docs section when docs are present', () => {
    renderResponse(SAMPLE_XML)
    expect(document.getElementById('docs-section').classList.contains('hidden')).toBe(false)
    const items = document.getElementById('docs').querySelectorAll('li')
    expect(items).toHaveLength(1)
  })

  it('hides docs section when docs are empty', () => {
    const xmlNoDocs = `<product_tag>Other</product_tag><summary>s</summary><root_cause>r</root_cause><debug_steps>Step 1: x</debug_steps><docs></docs>`
    renderResponse(xmlNoDocs)
    expect(document.getElementById('docs-section').classList.contains('hidden')).toBe(true)
  })
})

// ── newConversation ───────────────────────────────────────────────────────────

describe('newConversation', () => {
  it('clears the question textarea', () => {
    document.getElementById('question').value = 'some question'
    newConversation()
    expect(document.getElementById('question').value).toBe('')
  })

  it('hides the response area', () => {
    document.getElementById('response-area').classList.remove('hidden')
    newConversation()
    expect(document.getElementById('response-area').classList.contains('hidden')).toBe(true)
  })

  it('hides the error area', () => {
    document.getElementById('error-area').classList.remove('hidden')
    newConversation()
    expect(document.getElementById('error-area').classList.contains('hidden')).toBe(true)
  })
})

// ── copyResponse ──────────────────────────────────────────────────────────────

// Helper: mock innerText on all elements copyResponse reads (jsdom lacks innerText support)
function mockInnerText(id, value) {
  const el = document.getElementById(id)
  Object.defineProperty(el, 'innerText', { get: () => value, configurable: true })
}

describe('copyResponse', () => {
  it('calls clipboard.writeText with formatted response sections', async () => {
    // jsdom does not implement innerText; mock it via property descriptor for all four ids
    mockInnerText('summary', 'A test summary.')
    mockInnerText('root-cause', 'The root cause.')
    mockInnerText('debug-steps', '') // empty → filtered out
    mockInnerText('docs', '')        // empty → filtered out

    copyResponse()
    await Promise.resolve() // flush the .then() microtask

    expect(navigator.clipboard.writeText).toHaveBeenCalledOnce()
    const written = navigator.clipboard.writeText.mock.calls[0][0]
    expect(written).toContain('Summary')
    expect(written).toContain('A test summary.')
    expect(written).toContain('Root Cause')
    expect(written).toContain('The root cause.')
  })

  it('changes copy-btn label to "Copied!" after clipboard write', async () => {
    mockInnerText('summary', 'x')
    mockInnerText('root-cause', '')
    mockInnerText('debug-steps', '')
    mockInnerText('docs', '')

    copyResponse()
    await Promise.resolve()

    expect(document.getElementById('copy-btn').textContent).toBe('Copied!')
  })
})

// ── shareResponse ─────────────────────────────────────────────────────────────

describe('shareResponse', () => {
  it('does not call clipboard when there is no active history entry', () => {
    // activeHistoryId is null by default in a fresh module import
    shareResponse()
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled()
  })
})
