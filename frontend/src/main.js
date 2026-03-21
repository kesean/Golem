import { Clerk } from '@clerk/clerk-js'
import { ConvexClient } from 'convex/browser'
import './style.css'
import { askQuestion, clearHistory, initApp } from './app.js'

const clerk = new Clerk(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
await clerk.load()

const authWall = document.getElementById('auth-wall')

async function showApp() {
  const convex = new ConvexClient(import.meta.env.VITE_CONVEX_URL)

  window.askQuestion = askQuestion
  window.clearHistory = clearHistory

  document.getElementById('sign-out-btn').addEventListener('click', async () => {
    await clerk.signOut()
    window.location.reload()
  })

  await initApp({
    convex,
    userId: clerk.user.id,
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
