/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 3: Stream XML chunks from /ask/stream.
 * Phase 4: ES module — imported by main.js, functions exposed via window.*
 * US3: History stored in Convex (per-user, cloud-persisted).
 */

import { api } from '../convex/_generated/api.js'

// ─── Module state (set by initApp) ────────────────────────────────────────────

let _convex = null
let _getToken = null
let activeHistoryId = null

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

export async function clearHistory() {
  if (!_convex) return
  await _convex.mutation(api.history.clear, {})
  activeHistoryId = null
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
  list.innerHTML = ''

  if (history.length === 0) {
    const empty = document.createElement('li')
    empty.className = 'history-empty'
    empty.textContent = 'No history yet.'
    list.appendChild(empty)
    return
  }

  history.forEach(entry => {
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
    li.addEventListener('click', () => loadHistoryEntry(entry))
    list.appendChild(li)
  })
}

function loadHistoryEntry(entry) {
  activeHistoryId = entry._id
  renderHistorySidebar()
  document.getElementById('question').value = entry.question
  document.getElementById('error-area').classList.add('hidden')
  renderResponse(entry.rawXml)
}

// ─── XML parser ───────────────────────────────────────────────────────────────

function extractSection(text, tag) {
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

function renderResponse(accumulated) {
  const productTag = extractSection(accumulated, 'product_tag')
  const summary    = extractSection(accumulated, 'summary')
  const rootCause  = extractSection(accumulated, 'root_cause')
  const debugSteps = extractSection(accumulated, 'debug_steps')
  const docs       = extractSection(accumulated, 'docs')

  // Badge
  const badge = document.getElementById('product-tag-badge')
  badge.textContent = productTag?.content || ''
  badge.classList.toggle('hidden', !productTag?.content)

  // Summary
  document.getElementById('summary').textContent = summary?.content || ''

  // Root cause
  document.getElementById('root-cause').textContent = rootCause?.content || ''

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
        li.textContent = line
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

// ─── Main ask handler ────────────────────────────────────────────────────────

export async function askQuestion() {
  const questionEl   = document.getElementById('question')
  const btn          = document.getElementById('ask-btn')
  const responseArea = document.getElementById('response-area')
  const errorArea    = document.getElementById('error-area')
  const errorMsg     = document.getElementById('error-message')

  const question = questionEl.value.trim()
  if (!question) return

  responseArea.classList.add('hidden')
  responseArea.classList.remove('sections-ready')
  errorArea.classList.add('hidden')

  btn.disabled = true
  btn.innerHTML = '<span class="spinner"></span>Thinking…'

  try {
    const headers = { 'Content-Type': 'application/json' }
    if (_getToken) {
      const token = await _getToken()
      if (token) headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch('/ask/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify({ question }),
    })

    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.error || 'Something went wrong.')
    }

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let accumulated = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      accumulated += decoder.decode(value, { stream: true })
    }

    renderResponse(accumulated)

    activeHistoryId = await saveToHistory(question, accumulated)
    renderHistorySidebar()

  } catch (err) {
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
  document.getElementById('question').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askQuestion()
  })
}
