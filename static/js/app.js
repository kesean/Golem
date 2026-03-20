/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 3: Stream XML chunks from /ask/stream.
 *   Each chunk is parsed incrementally; new text fades in per section.
 *   History is stored in localStorage and replayed client-side (no API call).
 */

// ─── History (localStorage) ───────────────────────────────────────────────────

const HISTORY_KEY = 'devSupportHistory';
const MAX_HISTORY = 50;
let activeHistoryId = null;

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveToHistory(question, rawXml) {
  const history = loadHistory();
  const id = Date.now();
  history.push({ id, question, rawXml, timestamp: id });
  if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  return id;
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  activeHistoryId = null;
  renderHistorySidebar();
}

function formatRelativeTime(timestamp) {
  const diff = Date.now() - timestamp;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function renderHistorySidebar() {
  const list = document.getElementById('history-list');
  const history = loadHistory();
  list.innerHTML = '';

  if (history.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'history-empty';
    empty.textContent = 'No history yet.';
    list.appendChild(empty);
    return;
  }

  [...history].reverse().forEach(entry => {
    const li = document.createElement('li');
    li.className = 'history-item' + (entry.id === activeHistoryId ? ' active' : '');
    li.dataset.id = entry.id;

    const q = document.createElement('div');
    q.className = 'history-item-q';
    q.textContent = entry.question;

    const tagSection = extractSection(entry.rawXml, 'product_tag');
    const tagEl = document.createElement('div');
    tagEl.className = 'history-item-tag' + (tagSection?.content ? '' : ' hidden');
    tagEl.textContent = tagSection?.content || '';

    const t = document.createElement('div');
    t.className = 'history-item-time';
    t.textContent = formatRelativeTime(entry.timestamp);

    li.appendChild(q);
    li.appendChild(tagEl);
    li.appendChild(t);
    li.addEventListener('click', () => loadHistoryEntry(entry));
    list.appendChild(li);
  });
}

function loadHistoryEntry(entry) {
  activeHistoryId = entry.id;
  renderHistorySidebar();

  document.getElementById('question').value = entry.question;
  document.getElementById('error-area').classList.add('hidden');

  resetState();
  ['summary', 'root-cause', 'debug-steps', 'docs'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
  document.getElementById('docs-section').classList.add('hidden');
  const badge = document.getElementById('product-tag-badge');
  badge.textContent = '';
  badge.classList.add('hidden');

  const responseArea = document.getElementById('response-area');
  responseArea.classList.remove('hidden', 'fade-in');
  void responseArea.offsetWidth;
  responseArea.classList.add('fade-in');

  parseAndRender(entry.rawXml);

  // Stored response is complete — finalize any open list items
  if (!state.stepsClosed) {
    state.stepsClosed = true;
    finalizeList(document.getElementById('debug-steps'), false);
  }
  if (!state.docsClosed) {
    state.docsClosed = true;
    finalizeList(document.getElementById('docs'), true);
  }
}

// ─── Render state ────────────────────────────────────────────────────────────

const state = {
  summaryLen: 0,
  rootCauseLen: 0,
  stepsFinalized: 0,
  stepsClosed: false,
  docsFinalized: 0,
  docsClosed: false,
};

function resetState() {
  state.summaryLen = 0;
  state.rootCauseLen = 0;
  state.stepsFinalized = 0;
  state.stepsClosed = false;
  state.docsFinalized = 0;
  state.docsClosed = false;
}

// ─── DOM helpers ─────────────────────────────────────────────────────────────

function appendFadeSpan(el, newFullText, lenKey) {
  if (newFullText.length <= state[lenKey]) return;
  const chunk = newFullText.slice(state[lenKey]);
  state[lenKey] = newFullText.length;
  const span = document.createElement('span');
  span.className = 'chunk-fade';
  span.textContent = chunk;
  el.appendChild(span);
}

function applyDocContent(li, text) {
  li.innerHTML = '';
  if (/^https?:\/\//.test(text)) {
    const a = document.createElement('a');
    a.href = text;
    a.textContent = text;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    li.appendChild(a);
  } else {
    li.textContent = text;
  }
}

function updateListFade(listEl, lines, finalizedKey, isDocsType = false) {
  const prevFinalized = state[finalizedKey];
  const newFinalized = Math.max(0, lines.length - 1);

  // Commit any newly completed lines (all but the last)
  for (let i = prevFinalized; i < newFinalized; i++) {
    const li = document.createElement('li');
    li.className = 'chunk-fade';
    if (isDocsType) {
      applyDocContent(li, lines[i]);
    } else {
      li.textContent = lines[i];
    }
    listEl.appendChild(li);
  }
  state[finalizedKey] = newFinalized;

  if (lines.length === 0) return;

  // Update the currently-typing last item
  let typingLi = listEl.querySelector('li.typing');
  if (!typingLi) {
    typingLi = document.createElement('li');
    typingLi.className = 'typing chunk-fade';
    listEl.appendChild(typingLi);
  }
  typingLi.textContent = lines[lines.length - 1];
}

function finalizeList(listEl, isDocsType = false) {
  listEl.querySelectorAll('li.typing').forEach(li => {
    li.classList.remove('typing');
    if (isDocsType) applyDocContent(li, li.textContent.trim());
  });
}

// ─── XML stream parser ────────────────────────────────────────────────────────

function extractSection(text, tag) {
  const openIdx = text.indexOf(`<${tag}>`);
  if (openIdx === -1) return null;

  const contentStart = openIdx + tag.length + 2; // skip "<tag>"
  const closeIdx = text.indexOf(`</${tag}>`);
  const raw = closeIdx !== -1
    ? text.slice(contentStart, closeIdx)
    : text.slice(contentStart);

  let content = raw.trim();

  // While the section is still open, the buffer may end with a partial
  // closing tag (e.g. "</root_" before "</root_cause>" has fully arrived).
  // Strip it so it never gets rendered as visible text.
  if (closeIdx === -1) {
    const partialIdx = content.lastIndexOf('</');
    if (partialIdx !== -1) {
      const partial = content.slice(partialIdx);
      if (`</${tag}>`.startsWith(partial)) {
        content = content.slice(0, partialIdx).trimEnd();
      }
    }
  }

  return { content, closed: closeIdx !== -1 };
}

function parseAndRender(accumulated) {
  let anyContent = false;

  // ── Product tag ───────────────────────────────────────────────────────────
  const productTag = extractSection(accumulated, 'product_tag');
  if (productTag && productTag.content) {
    const badge = document.getElementById('product-tag-badge');
    badge.textContent = productTag.content;
    badge.classList.remove('hidden');
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  const summary = extractSection(accumulated, 'summary');
  if (summary) {
    appendFadeSpan(document.getElementById('summary'), summary.content, 'summaryLen');
    anyContent = true;
  }

  // ── Root Cause ────────────────────────────────────────────────────────────
  const rootCause = extractSection(accumulated, 'root_cause');
  if (rootCause) {
    appendFadeSpan(document.getElementById('root-cause'), rootCause.content, 'rootCauseLen');
    anyContent = true;
  }

  // ── Debug Steps ───────────────────────────────────────────────────────────
  const debugSteps = extractSection(accumulated, 'debug_steps');
  if (debugSteps && !state.stepsClosed) {
    const lines = debugSteps.content
      .split('\n')
      .map(l => l.replace(/^Step\s*\d+:\s*/i, '').trim())
      .filter(Boolean);

    if (lines.length > 0) {
      updateListFade(document.getElementById('debug-steps'), lines, 'stepsFinalized', false);
      anyContent = true;
    }
    if (debugSteps.closed) {
      state.stepsClosed = true;
      finalizeList(document.getElementById('debug-steps'), false);
    }
  } else if (debugSteps) {
    anyContent = true;
  }

  // ── Docs ──────────────────────────────────────────────────────────────────
  const docs = extractSection(accumulated, 'docs');
  const docsSection = document.getElementById('docs-section');
  if (docs && !state.docsClosed) {
    const lines = docs.content.split('\n').map(l => l.trim()).filter(Boolean);

    if (lines.length > 0) {
      updateListFade(document.getElementById('docs'), lines, 'docsFinalized', true);
      docsSection.classList.remove('hidden');
      anyContent = true;
    } else if (docs.closed) {
      docsSection.classList.add('hidden');
    }

    if (docs.closed) {
      state.docsClosed = true;
      finalizeList(document.getElementById('docs'), true);
    }
  } else if (docs) {
    anyContent = true;
  }

  return anyContent;
}

// ─── Main ask handler ────────────────────────────────────────────────────────

async function askQuestion() {
  const questionEl   = document.getElementById('question');
  const btn          = document.getElementById('ask-btn');
  const responseArea = document.getElementById('response-area');
  const errorArea    = document.getElementById('error-area');
  const errorMsg     = document.getElementById('error-message');

  const question = questionEl.value.trim();
  if (!question) return;

  // Reset UI and render state
  resetState();
  responseArea.classList.add('hidden');
  responseArea.classList.remove('fade-in');
  errorArea.classList.add('hidden');
  ['summary', 'root-cause', 'debug-steps', 'docs'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
  document.getElementById('docs-section').classList.add('hidden');
  const badge = document.getElementById('product-tag-badge');
  badge.textContent = '';
  badge.classList.add('hidden');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Thinking…';

  try {
    const res = await fetch('/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || 'Something went wrong.');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = '';
    let revealed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      accumulated += decoder.decode(value, { stream: true });
      const hasContent = parseAndRender(accumulated);

      if (hasContent && !revealed) {
        revealed = true;
        responseArea.classList.remove('hidden');
        void responseArea.offsetWidth; // force reflow so fade-in replays
        responseArea.classList.add('fade-in');
      }
    }

    // Final parse to ensure last chunk is fully rendered
    parseAndRender(accumulated);

    // Save to history and refresh sidebar
    activeHistoryId = saveToHistory(question, accumulated);
    renderHistorySidebar();

  } catch (err) {
    errorMsg.textContent = err.message;
    errorArea.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Ask';
  }
}

// ─── Keyboard shortcut ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderHistorySidebar();
  document.getElementById('question').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askQuestion();
  });
});
