import { useState } from 'react'
import { useUser, useClerk } from '@clerk/clerk-react'
import { useTheme } from './hooks/useTheme'
import { useChat } from './hooks/useChat'
import { Header } from './components/Header'
import { QuestionInput } from './components/QuestionInput'
import { ResponsePanel } from './components/ResponsePanel'
import { HistoryPalette } from './components/HistoryPalette'
import { SuggestedQuestions } from './components/SuggestedQuestions'
import type { HistoryEntry } from './hooks/useHistory'

function Layout({ userName, isGuest = false, onSignOut }: { userName?: string; isGuest?: boolean; onSignOut?: () => void }) {
  const { theme, toggle: toggleTheme } = useTheme()
  const chat = useChat(isGuest)
  const [question, setQuestion] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)

  function handleSubmit() {
    if (!question.trim() || chat.isLoading) return
    chat.ask(question)
    setQuestion('')
  }

  function handlePickSuggestion(q: string) {
    if (chat.isLoading) return
    chat.ask(q)
  }

  function handleHistorySelect(entry: HistoryEntry) {
    setQuestion(entry.question)
    chat.loadFromHistory(entry.rawXml)
  }

  function handleNewConversation() {
    setQuestion('')
    chat.reset()
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
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenHistory={() => setHistoryOpen(true)}
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
          onChange={setQuestion}
          onSubmit={handleSubmit}
          isLoading={chat.isLoading}
        />
        {!chat.isLoading && !chat.parsedResponse && !chat.error && !question.trim() && (
          <SuggestedQuestions onPick={handlePickSuggestion} />
        )}
        <ResponsePanel
          isLoading={chat.isLoading}
          isStreaming={chat.isStreaming}
          parsedResponse={chat.parsedResponse}
          error={chat.error}
          evalId={chat.evalId}
          historyId={chat.historyId}
          chunks={chat.chunks}
        />
      </main>

      <HistoryPalette
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        onSelect={handleHistorySelect}
        isGuest={isGuest}
      />
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
  if (import.meta.env.VITE_TEST_BYPASS_AUTH === 'true') {
    return <Layout />
  }
  return <AuthenticatedApp />
}
