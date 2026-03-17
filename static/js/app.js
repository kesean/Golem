/**
 * app.js — Frontend logic for the Dev Support AI chatbot.
 *
 * Phase 1: Basic fetch → display response.
 * Phase 2: Parse structured JSON fields and render sections.
 * Phase 3: Switch to fetch with streaming (ReadableStream).
 */

async function askQuestion() {
  const questionEl = document.getElementById("question");
  const btn = document.getElementById("ask-btn");
  const responseArea = document.getElementById("response-area");
  const answerEl = document.getElementById("answer");
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

    // Phase 1: show raw answer
    // Phase 2: you'll replace this with renderStructuredAnswer(data)
    answerEl.textContent = data.answer;
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
