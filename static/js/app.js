/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 3: Stream XML chunks from /ask/stream.
 *   Each chunk is parsed incrementally; new text fades in per section.
 */

// ─── Render state ────────────────────────────────────────────────────────────

const state = {
  summaryLen: 0,
  rootCauseLen: 0,
  stepsFinalized: 0,
  docsFinalized: 0,
};

function resetState() {
  state.summaryLen = 0;
  state.rootCauseLen = 0;
  state.stepsFinalized = 0;
  state.docsFinalized = 0;
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

  return { content: raw.trim(), closed: closeIdx !== -1 };
}

function parseAndRender(accumulated) {
  let anyContent = false;

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
  if (debugSteps) {
    const lines = debugSteps.content
      .split('\n')
      .map(l => l.replace(/^Step\s*\d+:\s*/i, '').trim())
      .filter(Boolean);

    if (lines.length > 0) {
      updateListFade(document.getElementById('debug-steps'), lines, 'stepsFinalized', false);
      anyContent = true;
    }
    if (debugSteps.closed) {
      finalizeList(document.getElementById('debug-steps'), false);
    }
  }

  // ── Docs ──────────────────────────────────────────────────────────────────
  const docs = extractSection(accumulated, 'docs');
  const docsSection = document.getElementById('docs-section');
  if (docs) {
    const lines = docs.content.split('\n').map(l => l.trim()).filter(Boolean);

    if (lines.length > 0) {
      updateListFade(document.getElementById('docs'), lines, 'docsFinalized', true);
      docsSection.classList.remove('hidden');
      anyContent = true;
    } else if (docs.closed) {
      docsSection.classList.add('hidden');
    }

    if (docs.closed) {
      finalizeList(document.getElementById('docs'), true);
    }
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
  document.getElementById('question').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askQuestion();
  });
});
