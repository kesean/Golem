import { ConvexClient } from 'convex/browser'
import './style.css'
import { askQuestion, clearHistory, newConversation, copyResponse, shareResponse, thumbFeedback, initApp } from './app.js'

const authWall = document.getElementById('auth-wall')

if (import.meta.env.VITE_TEST_BYPASS_AUTH === 'true') {
  // Test mode: skip Clerk entirely, show app with a mock Convex client.
  // Only active when VITE_TEST_BYPASS_AUTH=true — never in production.
  const mockConvex = {
    query:    async () => [],
    mutation: async () => 'mock-id',
    setAuth:  () => {},
  }

  window.askQuestion    = askQuestion
  window.clearHistory   = clearHistory
  window.newConversation = newConversation
  window.copyResponse   = copyResponse
  window.shareResponse  = shareResponse
  window.thumbFeedback  = thumbFeedback

  document.getElementById('sign-out-btn').addEventListener('click', () => {})

  await initApp({ convex: mockConvex, getToken: async () => 'mock-token' })

  authWall.style.display = 'none'
  document.getElementById('app-root').style.display = ''
  document.body.style.visibility = 'visible'
} else {
  // Production mode: require Clerk auth.
  const { Clerk } = await import('@clerk/clerk-js')
  const clerk = new Clerk(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
  await clerk.load()

  async function showApp() {
    const convex = new ConvexClient(import.meta.env.VITE_CONVEX_URL)

    convex.setAuth(async ({ forceRefreshToken }) => {
      return await clerk.session?.getToken({ template: 'convex' }) ?? null
    })

    window.askQuestion    = askQuestion
    window.clearHistory   = clearHistory
    window.newConversation = newConversation
    window.copyResponse   = copyResponse
    window.shareResponse  = shareResponse
    window.thumbFeedback  = thumbFeedback

    document.getElementById('sign-out-btn').addEventListener('click', async () => {
      await clerk.signOut()
      window.location.reload()
    })

    await initApp({
      convex,
      getToken: () => clerk.session?.getToken(),
    })

    authWall.style.display = 'none'
    document.getElementById('app-root').style.display = ''
    document.body.style.visibility = 'visible'
  }

  if (clerk.user) {
    await showApp()
  } else {
    await clerk.redirectToSignIn({ redirectUrl: window.location.href })
  }
}
