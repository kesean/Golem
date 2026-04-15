import { Clerk } from '@clerk/clerk-js'
import { ConvexClient } from 'convex/browser'
import './style.css'
import { askQuestion, clearHistory, newConversation, copyResponse, shareResponse, thumbFeedback, initApp } from './app.js'

const clerk = new Clerk(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
await clerk.load()

const authWall = document.getElementById('auth-wall')

async function showApp() {
  const convex = new ConvexClient(import.meta.env.VITE_CONVEX_URL)

  // Authenticate the Convex client with the Clerk "convex" JWT template
  convex.setAuth(async ({ forceRefreshToken }) => {
    return await clerk.session?.getToken({ template: 'convex' }) ?? null
  })

  window.askQuestion = askQuestion
  window.clearHistory = clearHistory
  window.newConversation = newConversation
  window.copyResponse = copyResponse
  window.shareResponse = shareResponse
  window.thumbFeedback = thumbFeedback

  document.getElementById('sign-out-btn').addEventListener('click', async () => {
    await clerk.signOut()
    window.location.reload()
  })

  await initApp({
    convex,
    getToken: () => clerk.session?.getToken(),
  })

  // Reveal UI only after full setup so onclick handlers are always defined
  authWall.style.display = 'none'
  document.getElementById('app-root').style.display = ''
  document.body.style.visibility = 'visible'
}

if (clerk.user) {
  await showApp()
} else {
  await clerk.redirectToSignIn({ redirectUrl: window.location.href })
}
