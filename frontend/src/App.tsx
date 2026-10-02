import { useEffect, useRef, useState } from 'react'
import { useUser, useClerk } from '@clerk/clerk-react'
import { useTheme } from './hooks/useTheme'
import { useChat } from './hooks/useChat'
import { Header } from './components/Header'
import { QuestionInput } from './components/QuestionInput'
import { ResponsePanel } from './components/ResponsePanel'
import { HistoryPalette } from './components/HistoryPalette'
import { SuggestedQuestions } from './components/SuggestedQuestions'
import { TourDialog } from './components/TourDialog'
import { SharedNotice } from './components/SharedNotice'
import { useSharedEntry, sharedViewFor } from './hooks/useSharedEntry'
import { hasSeenTour, markTourSeen } from './lib/tour'
import type { HistoryEntry } from './hooks/useHistory'

const bypassAuth = import.meta.env.VITE_TEST_BYPASS_AUTH === 'true'

function Layout({ userName, isGuest = false, onSignOut }: { userName?: string; isGuest?: boolean; onSignOut?: () => void }) {
  const { theme, toggle: toggleTheme } = useTheme()
  const chat = useChat(isGuest)
  const [question, setQuestion] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const sharedEntry = useSharedEntry()
  // Once the user starts their own work, a share lookup that resolves late is ignored.
  const [userActed, setUserActed] = useState(false)
  const sharedView = sharedViewFor(sharedEntry, userActed)

  useEffect(() => {
    if (sharedEntry.status !== 'found' || userActed) return
    setQuestion(sharedEntry.question)
    chat.loadFromHistory(sharedEntry.rawXml, sharedEntry.id)
    // Runs once per lookup result; chat's functions are not referentially stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sharedEntry.status])

  const refocusQuestion = useRef(false)
  // The textarea is disabled while loading, so restore focus once it re-enables
  useEffect(() => {
    if (!chat.isLoading && refocusQuestion.current) {
      refocusQuestion.current = false
      document.getElementById('question')?.focus()
    }
  }, [chat.isLoading])

  // A shared answer shouldn't open under the tour's modal; the tour still shows on a later visit.
  const [tourOpen, setTourOpen] = useState(
    () => !hasSeenTour() && !new URLSearchParams(window.location.search).has('share'),
  )

  function closeTour() {
    markTourSeen()
    setTourOpen(false)
  }

  function handleSubmit() {
    if (!question.trim() || chat.isLoading) return
    setUserActed(true)
    chat.ask(question)
    setQuestion('')
  }

  function handlePickSuggestion(q: string) {
    if (chat.isLoading) return
    setUserActed(true)
    setQuestion(q)
    chat.ask(q)
    // The chip unmounts once loading starts; move focus to the input when it re-enables
    refocusQuestion.current = true
  }

  function handleHistorySelect(entry: HistoryEntry) {
    setUserActed(true)
    setQuestion(entry.question)
    chat.loadFromHistory(entry.rawXml)
  }

  function handleNewConversation() {
    setUserActed(true)
    setQuestion('')
    chat.reset()
  }

  function handleQuestionChange(value: string) {
    setUserActed(true)
    setQuestion(value)
  }

  function handleAskOwn() {
    setUserActed(true)
    setQuestion('')
    chat.reset()
    document.getElementById('question')?.focus()
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <a href="#question" className="skip-link">
        Skip to question
      </a>
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenTour={() => setTourOpen(true)}
        onNewConversation={handleNewConversation}
        userName={userName}
        onSignOut={onSignOut}
      />

      <main
        style={{
          flex: 1,
          maxWidth: '760px',
          width: '100%',
          margin: '0 auto',
          padding: '32px 0',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <QuestionInput
          value={question}
          onChange={handleQuestionChange}
          onSubmit={handleSubmit}
          isLoading={chat.isLoading}
          hero={!chat.isLoading && !chat.parsedResponse && !chat.error}
        />
        {!chat.isLoading && !chat.parsedResponse && !chat.error && !question.trim() &&
          sharedEntry.status !== 'loading' && sharedView === 'none' && (
          <SuggestedQuestions onPick={handlePickSuggestion} />
        )}
        {sharedView !== 'none' && <SharedNotice view={sharedView} onAskOwn={handleAskOwn} />}
        <ResponsePanel
          isLoading={chat.isLoading}
          isStreaming={chat.isStreaming}
          parsedResponse={chat.parsedResponse}
          error={chat.error}
          evalId={chat.evalId}
          historyId={chat.historyId}
          chunks={chat.chunks}
          isShared={sharedView === 'found'}
        />
      </main>

      <HistoryPalette
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        onSelect={handleHistorySelect}
        isGuest={isGuest}
      />

      <TourDialog open={tourOpen} onClose={closeTour} />
    </div>
  )
}

function AuthenticatedApp() {
  const { isSignedIn, isLoaded, user } = useUser()
  const { signOut } = useClerk()
  if (!isLoaded) return null
  return (
    <Layout
      isGuest={!isSignedIn}
      userName={isSignedIn ? (user?.firstName ?? undefined) : undefined}
      onSignOut={isSignedIn ? () => signOut() : undefined}
    />
  )
}

export default function App() {
  if (bypassAuth) {
    return <Layout />
  }
  return <AuthenticatedApp />
}
