# React + TypeScript Migration — Design Spec

**Date:** 2026-04-23
**Phase:** V2d (frontend upgrade)
**Scope:** In-place migration of `frontend/` from Vanilla JS + Vite to React + TypeScript + shadcn/ui. Backend unchanged.

---

## Overview

The current frontend is two large JS files (`main.js`, `app.js`) with module-level mutable state and imperative DOM manipulation. This migration converts it to a typed React component tree with custom hooks, using shadcn/ui as the component library and the design system established in `design-preview.html` (Newsreader + JetBrains Mono + DM Sans, forest green accent, light/dark toggle).

The debug panel (showing retrieved doc chunks) is explicitly out of scope — it requires a backend `/ask` response change and will be added as a focused follow-on feature.

---

## Migration Strategy

**In-place conversion** — the existing `frontend/` Vite project is modified directly. Clerk/Convex wiring, Playwright config, Vercel config (`vercel.json`), and CI workflows remain unchanged. This avoids re-doing setup that already works.

---

## Component Hierarchy

```
main.tsx                    — ClerkProvider + ConvexProvider, test bypass gate
└── <App>                   — theme state (useTheme), auth gate
    └── <Layout>
        ├── <Header>         — logo, theme toggle, history trigger (⌘K)
        ├── <QuestionInput>  — textarea, ask button, Ctrl+↵ shortcut
        ├── <ResponsePanel>  — skeleton or response cards
        │   ├── <ProductBadge>
        │   ├── <SectionCard> × 4  (summary, root cause, steps, docs)
        │   ├── <FeedbackButtons>
        │   └── <ResponseActions>  (copy, share)
        └── <HistoryPalette> — ⌘K command palette, Convex history list
```

All visual styling follows `design-preview.html`: warm off-white / deep slate backgrounds, Newsreader serif for response content, JetBrains Mono for input and code spans, DM Sans for chrome.

---

## File Structure

```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── ui/              — shadcn generated (Button, Textarea, Dialog…)
│   │   ├── Header.tsx
│   │   ├── QuestionInput.tsx
│   │   ├── ResponsePanel.tsx
│   │   ├── SectionCard.tsx
│   │   ├── ProductBadge.tsx
│   │   ├── FeedbackButtons.tsx
│   │   ├── ResponseActions.tsx
│   │   └── HistoryPalette.tsx
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useHistory.ts
│   │   └── useTheme.ts
│   ├── lib/
│   │   ├── parseResponse.ts
│   │   └── utils.ts         — shadcn cn() utility
│   ├── types/
│   │   └── index.ts
│   ├── globals.css          — shadcn theming layer + design tokens
│   └── style.css            — kept for any remaining custom styles
├── tsconfig.json            — new
├── vite.config.ts           — renamed, +react() plugin
└── package.json             — updated deps (see Dependencies section)
```

---

## Data Flow

1. User types a question and submits via button or `Ctrl+↵`
2. `<QuestionInput>` calls `useChat.ask(question)`
3. `useChat` sets `isLoading = true`, appends to `conversationHistory`, fetches a Clerk token via `useAuth()`, then `POST /ask { question, history }`
4. Flask verifies the JWT, rate-limits, runs `chat.run()` → Claude tool loop → returns `{ response, input_tokens, output_tokens, latency_ms }`
5. `useChat` calls `parseResponse(xml)` → `ParsedResponse`, sets state, caps history at 20 messages
6. `useHistory().save()` calls the Convex `history.add` mutation (awaited)
7. `evals.createEval` fires and forgets — `evalId` stored in `useChat` state for feedback
8. `<ResponsePanel>` receives `parsedResponse` and renders `<SectionCard>` components with staggered CSS animation
9. `<FeedbackButtons>` receives `evalId` and calls `evals.setFeedback` on click

---

## TypeScript Types

```ts
// src/types/index.ts

type ParsedResponse = {
  productTag: string
  summary: string
  rootCause: string
  debugSteps: string[]
  docs: string[]
}

type ChatMessage = { role: 'user' | 'assistant'; content: string }

type UseChatReturn = {
  ask: (question: string) => Promise<void>
  parsedResponse: ParsedResponse | null
  isLoading: boolean
  error: string | null       // always a sanitized user-facing message
  evalId: string | null
  reset: () => void
}
```

`parseResponse(xml: string): ParsedResponse` lives in `lib/parseResponse.ts` as a pure function with no React dependency.

---

## Auth Wiring

`@clerk/clerk-js` is replaced by `@clerk/clerk-react`.

- `main.tsx` wraps the tree in `<ClerkProvider publishableKey={...}>` and `<ConvexProviderWithClerk>` (from `convex/react-clerk`, already installed)
- `useAuth()` provides `getToken()` for attaching Bearer tokens to `/ask` requests
- `useUser()` provides the user object where needed (e.g. sign-out button in `<Header>`)
- Test bypass (`VITE_TEST_BYPASS_AUTH=true`) is handled before providers mount in `main.tsx`, injecting a mock Convex client identical to the current approach

---

## Error Handling

`useChat` catches all errors from the `/ask` fetch and maps them as follows:

| HTTP status | User-facing message |
|---|---|
| 429 | "You've reached the daily limit — try again tomorrow." |
| All others | "Something went wrong. Please try again." |

Raw error details are logged to `console.error` in dev only (`import.meta.env.DEV`). A `// TODO: send to error logging middleware` stub sits alongside that log, ready for the backend hook. No raw server response text ever reaches a rendered component.

---

## Component Library

**shadcn/ui** — installed via CLI, components owned in `components/ui/`. Tailwind CSS is required.

Components used initially: `Button`, `Textarea`, `Dialog` (command palette), `Skeleton`. Additional components added on demand as needed.

The design token system from `design-preview.html` (CSS custom properties for `--bg`, `--accent`, `--text-primary`, etc.) is ported into `globals.css` as shadcn's theming layer, preserving the exact light/dark values established in the prototype.

---

## Testing

| Layer | Tool | Change |
|---|---|---|
| Unit | Vitest | `tests/app.test.js` → `tests/parseResponse.test.ts` (tests `lib/parseResponse.ts`) |
| E2E | Playwright | **No changes** — runs against the built app, framework-agnostic |

No React Testing Library added at this stage — the Playwright e2e suite covers the user-facing behaviour that matters, and `parseResponse.ts` is the only logic worth unit testing independently.

---

## Dependencies Added

```json
"react": "^19",
"react-dom": "^19",
"@clerk/clerk-react": "^5",
"tailwindcss": "^4",
"@tailwindcss/vite": "^4"
```

```json
"devDependencies": {
  "@types/react": "^19",
  "@types/react-dom": "^19",
  "@vitejs/plugin-react": "^4"
}
```

shadcn/ui components are copied into the repo via CLI (`npx shadcn@latest add ...`) — no runtime package added.

**Kept:** `marked` (used in `<SectionCard>` for markdown rendering of response content), `convex`, `convex-test`

**Removed:** `@clerk/clerk-js` (replaced by `@clerk/clerk-react`)

---

## Out of Scope

- Debug panel (retrieved doc chunks) — requires backend `/ask` response change; planned as follow-on
- React Testing Library — not needed given Playwright coverage
- React Router — app remains single-page; share links use query params as before
- Zustand or other state libraries — `useChat` + component state is sufficient
