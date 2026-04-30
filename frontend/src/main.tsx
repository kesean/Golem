/// <reference types="vite/client" />
import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { ConvexReactClient, ConvexProvider } from 'convex/react'
import { ConvexProviderWithClerk as ConvexWithClerk } from 'convex/react-clerk'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { TokenContext } from './contexts/TokenContext'
import { getGuestToken } from './lib/guestAuth'
import App from './App'
import './globals.css'

const convex = new ConvexReactClient(import.meta.env.VITE_CONVEX_URL as string)

function AuthTokenProvider({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth()
  return (
    <TokenContext.Provider value={{ getToken: () => getToken({ template: 'convex' }) }}>
      {children}
    </TokenContext.Provider>
  )
}

function GuestTokenProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    getGuestToken()
      .then(t => { setToken(t); setReady(true) })
      .catch(() => setReady(true))
  }, [])

  if (!ready) {
    return (
      <div
        style={{
          minHeight: '100vh',
          backgroundColor: 'var(--bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <span key={i} className="thinking-dot" style={{ animationDelay: `${i * 0.16}s` }} />
          ))}
        </div>
        <span
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '13px',
            color: 'var(--text-secondary)',
          }}
        >
          Loading…
        </span>
      </div>
    )
  }

  return (
    <TokenContext.Provider value={{ getToken: async () => token }}>
      {children}
    </TokenContext.Provider>
  )
}

function AuthRouter() {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return null

  if (isSignedIn) {
    return (
      <ConvexWithClerk client={convex} useAuth={useAuth}>
        <AuthTokenProvider>
          <App />
        </AuthTokenProvider>
      </ConvexWithClerk>
    )
  }

  return (
    <ConvexProvider client={convex}>
      <GuestTokenProvider>
        <App />
      </GuestTokenProvider>
    </ConvexProvider>
  )
}

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement)

if (import.meta.env.VITE_TEST_BYPASS_AUTH === 'true') {
  root.render(
    <ConvexProvider client={convex}>
      <TokenContext.Provider value={{ getToken: async () => null }}>
        <App />
      </TokenContext.Provider>
    </ConvexProvider>
  )
} else {
  root.render(
    <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string}>
      <AuthRouter />
    </ClerkProvider>
  )
}
