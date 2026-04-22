/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 3: Render XML response from /ask.
 * Phase 4: ES module — imported by main.js, functions exposed via window.*
 * US3: History stored in Convex (per-user, cloud-persisted).
 */

import { marked } from 'marked'
import { api } from '../convex/_generated/api.js'

marked.setOptions({ breaks: true })

// ─── Module state (set by initApp) ────────────────────────────────────────────

let _convex = null
let _getToken = null
let activeHistoryId = null
let _conversationHistory = []  // [{role, content}, ...] sent to Claude each turn
let _currentEvalId = null

// ─── History (Convex) ─────────────────────────────────────────────────────────

async function loadHistory() {
  if (!_convex) return []
  try {
    return await _convex.query(api.history.list, {})
  } catch {
    return []
  }
}

async function saveToHistory(question, rawXml) {
  if (!_convex) return null
  return await _convex.mutation(api.history.add, { question, rawXml })
}

// ─── Feedback helpers ─────────────────────────────────────────────────────────

function _resetFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.classList.remove('active-up')
  down.classList.remove('active-down')
}

function _enableFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.disabled   = false
  down.disabled = false
}

function _disableFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.disabled   = true
  down.disabled = true
}

export function shareResponse() {
  if (!activeHistoryId) return
  const url = `${window.location.origin}${window.location.pathname}?share=${activeHistoryId}`
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('share-btn')
    btn.textContent = 'Copied link!'
    setTimeout(() => { btn.textContent = 'Share' }, 2000)
  })
}

export function copyResponse() {
  const parts = [
    ['Summary', 'summary'],
    ['Root Cause', 'root-cause'],
    ['Debug Steps', 'debug-steps'],
    ['Docs', 'docs'],
  ]
  const text = parts
    .map(([label, id]) => {
      const content = document.getElementById(id)?.innerText.trim()
      return content ? `${label}\n${content}` : ''
    })
    .filter(Boolean)
    .join('\n\n')

  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copy-btn')
    btn.textContent = 'Copied!'
    setTimeout(() => { btn.textContent = 'Copy' }, 2000)
  })
}

export function newConversation() {
  _conversationHistory = []
  activeHistoryId = null
  _currentEvalId = null
  _resetFeedback()
  _disableFeedback()
  document.getElementById('question').value = ''
  document.getElementById('response-area').classList.add('hidden')
  document.getElementById('error-area').classList.add('hidden')
  renderHistorySidebar()
}

export async function clearHistory() {
  if (!_convex) return
  await _convex.mutation(api.history.clear, {})
  activeHistoryId = null
  _conversationHistory = []
  renderHistorySidebar()
}

function formatRelativeTime(timestamp) {
  const diff = Date.now() - timestamp
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

async function renderHistorySidebar() {
  const list = document.getElementById('history-list')
  const history = await loadHistory()
  const term = document.getElementById('history-search')?.value.toLowerCase() || ''
  const filtered = term ? history.filter(e => e.question.toLowerCase().includes(term)) : history
  list.innerHTML = ''

  if (filtered.length === 0) {
    const empty = document.createElement('li')
    empty.className = 'history-empty'
    empty.textContent = 'No history yet.'
    list.appendChild(empty)
    return
  }

  filtered.forEach(entry => {
    const li = document.createElement('li')
    li.className = 'history-item' + (entry._id === activeHistoryId ? ' active' : '')
    li.dataset.id = entry._id

    const q = document.createElement('div')
    q.className = 'history-item-q'
    q.textContent = entry.question

    const tagSection = extractSection(entry.rawXml, 'product_tag')
    const tagEl = document.createElement('div')
    tagEl.className = 'history-item-tag' + (tagSection?.content ? '' : ' hidden')
    tagEl.textContent = tagSection?.content || ''

    const t = document.createElement('div')
    t.className = 'history-item-time'
    t.textContent = formatRelativeTime(entry._creationTime)

    li.appendChild(q)
    li.appendChild(tagEl)
    li.appendChild(t)
    li.setAttribute('tabindex', '0')
    li.setAttribute('role', 'button')
    li.setAttribute('aria-label', entry.question)
    li.addEventListener('click', () => loadHistoryEntry(entry))
    li.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); loadHistoryEntry(entry) }
    })
    list.appendChild(li)
  })
}

function loadHistoryEntry(entry) {
  activeHistoryId = entry._id
  _conversationHistory = []  // history entries start a fresh context
  _currentEvalId = null
  _resetFeedback()
  _disableFeedback()
  renderHistorySidebar()
  document.getElementById('question').value = entry.question
  document.getElementById('error-area').classList.add('hidden')
  renderResponse(entry.rawXml)
}

// ─── XML parser ───────────────────────────────────────────────────────────────

export function extractSection(text, tag) {
  const openIdx = text.indexOf(`<${tag}>`)
  if (openIdx === -1) return null
  const contentStart = openIdx + tag.length + 2
  const closeIdx = text.indexOf(`</${tag}>`)
  const content = closeIdx !== -1
    ? text.slice(contentStart, closeIdx).trim()
    : text.slice(contentStart).trim()
  return { content, closed: closeIdx !== -1 }
}

// ─── Render full response ─────────────────────────────────────────────────────

export function renderResponse(xmlText) {
  const productTag = extractSection(xmlText, 'product_tag')
  const summary    = extractSection(xmlText, 'summary')
  const rootCause  = extractSection(xmlText, 'root_cause')
  const debugSteps = extractSection(xmlText, 'debug_steps')
  const docs       = extractSection(xmlText, 'docs')

  // Badge
  const badge = document.getElementById('product-tag-badge')
  badge.textContent = productTag?.content || ''
  badge.classList.toggle('hidden', !productTag?.content)

  // Summary
  document.getElementById('summary').innerHTML = marked.parse(summary?.content || '')

  // Root cause
  document.getElementById('root-cause').innerHTML = marked.parse(rootCause?.content || '')

  // Debug steps
  const stepsEl = document.getElementById('debug-steps')
  stepsEl.innerHTML = ''
  if (debugSteps?.content) {
    debugSteps.content
      .split('\n')
      .map(l => l.replace(/^Step\s*\d+:\s*/i, '').trim())
      .filter(Boolean)
      .forEach(line => {
        const li = document.createElement('li')
        li.innerHTML = marked.parseInline(line)
        stepsEl.appendChild(li)
      })
  }

  // Docs
  const docsEl      = document.getElementById('docs')
  const docsSection = document.getElementById('docs-section')
  docsEl.innerHTML  = ''
  const docLines = docs?.content
    ? docs.content.split('\n').map(l => l.trim()).filter(Boolean)
    : []

  if (docLines.length > 0) {
    docLines.forEach(line => {
      const li = document.createElement('li')
      if (/^https?:\/\//.test(line)) {
        const a = document.createElement('a')
        a.href = line
        a.textContent = line
        a.target = '_blank'
        a.rel = 'noopener noreferrer'
        li.appendChild(a)
      } else {
        li.textContent = line
      }
      docsEl.appendChild(li)
    })
    docsSection.classList.remove('hidden')
  } else {
    docsSection.classList.add('hidden')
  }

  // Trigger staggered section fade-in by re-inserting the class
  const responseArea = document.getElementById('response-area')
  responseArea.classList.remove('hidden', 'sections-ready')
  void responseArea.offsetWidth
  responseArea.classList.add('sections-ready')
}

export async function thumbFeedback(type) {
  if (!_currentEvalId || !_convex) return
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return

  const isAlreadyActive =
    (type === 'up'   && up.classList.contains('active-up')) ||
    (type === 'down' && down.classList.contains('active-down'))

  _resetFeedback()
  const newFeedback = isAlreadyActive ? undefined : type
  if (newFeedback === 'up')   up.classList.add('active-up')
  if (newFeedback === 'down') down.classList.add('active-down')

  await _convex.mutation(api.evals.setFeedback, {
    evalId: _currentEvalId,
    feedback: newFeedback,
  })
}

// ─── Main ask handler ────────────────────────────────────────────────────────

export async function askQuestion() {
  const questionEl   = document.getElementById('question')
  const btn          = document.getElementById('ask-btn')
  const responseArea = document.getElementById('response-area')
  const errorArea    = document.getElementById('error-area')
  const errorMsg     = document.getElementById('error-message')

  const question = questionEl.value.trim()
  if (!question) return

  const skeleton = document.getElementById('skeleton')
  responseArea.classList.add('hidden')
  responseArea.classList.remove('sections-ready')
  errorArea.classList.add('hidden')
  skeleton.classList.remove('hidden')

  btn.disabled = true
  btn.textContent = 'Thinking…'

  try {
    const headers = { 'Content-Type': 'application/json' }
    if (_getToken) {
      const token = await _getToken()
      if (token) headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/ask`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question, history: _conversationHistory }),
    })

    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.error || 'Something went wrong.')
    }

    const { response, input_tokens, output_tokens, latency_ms } = await res.json()

    skeleton.classList.add('hidden')
    renderResponse(response)

    // Append to in-memory conversation (cap at 10 turns = 20 messages)
    _conversationHistory.push({ role: 'user', content: question })
    _conversationHistory.push({ role: 'assistant', content: response })
    if (_conversationHistory.length > 20) _conversationHistory.splice(0, 2)

    activeHistoryId = await saveToHistory(question, response)
    if (_convex) {
      _currentEvalId = await _convex.mutation(api.evals.createEval, {
        question,
        response,
        latency_ms,
        input_tokens,
        output_tokens,
      })
    }
    _resetFeedback()
    _enableFeedback()
    renderHistorySidebar()

  } catch (err) {
    skeleton.classList.add('hidden')
    errorMsg.textContent = err.message
    errorArea.classList.remove('hidden')
  } finally {
    btn.disabled = false
    btn.textContent = 'Ask'
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

export async function initApp({ convex, getToken }) {
  _convex   = convex
  _getToken = getToken
  await renderHistorySidebar()

  window._filterHistory = () => renderHistorySidebar()

  // Load shared response if ?share= param is present
  const shareId = new URLSearchParams(window.location.search).get('share')
  if (shareId && _convex) {
    const entry = await _convex.query(api.history.getById, { id: shareId })
    if (entry) {
      activeHistoryId = entry._id
      document.getElementById('question').value = entry.question
      renderResponse(entry.rawXml)
    }
    // Clean up URL without reload
    window.history.replaceState({}, '', window.location.pathname)
  }

  const isMac = navigator.userAgentData?.platform === 'macOS' || /Mac/.test(navigator.userAgent)
  document.getElementById('shortcut-hint').textContent = isMac ? '⌘↵ to submit' : 'Ctrl+↵ to submit'

  document.getElementById('question').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askQuestion()
  })
}
