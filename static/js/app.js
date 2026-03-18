/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 2: Parse structured JSON fields and render sections.
 * Phase 3: Switch to fetch with streaming (ReadableStream).
 */

function renderStructuredAnswer(data) {
  document.getElementById("summary").textContent = data.summary || "";
  document.getElementById("root-cause").textContent = data.root_cause || "";

  const stepsList = document.getElementById("debug-steps");
  stepsList.innerHTML = "";
  (data.debug_steps || []).forEach((step) => {
    const li = document.createElement("li");
    li.textContent = step;
    stepsList.appendChild(li);
  });

  const docsList = document.getElementById("docs");
  const docsSection = document.getElementById("docs-section");
  docsList.innerHTML = "";
  if (data.docs && data.docs.length > 0) {
    data.docs.forEach((doc) => {
      const li = document.createElement("li");
      // If it looks like a URL, render it as a link
      if (/^https?:\/\//.test(doc)) {
        const a = document.createElement("a");
        a.href = doc;
        a.textContent = doc;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
      } else {
        li.textContent = doc;
      }
      docsList.appendChild(li);
    });
    docsSection.classList.remove("hidden");
  } else {
    docsSection.classList.add("hidden");
  }
}

async function askQuestion() {
  const questionEl = document.getElementById("question");
  const btn = document.getElementById("ask-btn");
  const responseArea = document.getElementById("response-area");
  const errorArea = document.getElementById("error-area");
  const errorMsg = document.getElementById("error-message");

  const question = questionEl.value.trim();
  if (!question) return;

  // Reset UI
  responseArea.classList.add("hidden");
  errorArea.classList.add("hidden");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Thinking…';

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "Something went wrong.");
    }

    renderStructuredAnswer(data);
    responseArea.classList.remove("hidden");

  } catch (err) {
    errorMsg.textContent = err.message;
    errorArea.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Ask";
  }
}

// Allow Cmd/Ctrl+Enter to submit
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("question").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      askQuestion();
    }
  });
});
