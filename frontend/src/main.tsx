/// <reference types="vite/client" />
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConvexReactClient } from 'convex/react'
import { ConvexProvider } from 'convex/react'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { ConvexProviderWithClerk } from 'convex/react-clerk'
import { TokenContext } from './contexts/TokenContext'
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
      <ConvexProviderWithClerk client={convex} useAuth={useAuth}>
        <AuthTokenProvider>
          <App />
        </AuthTokenProvider>
      </ConvexProviderWithClerk>
    </ClerkProvider>
  )
}
