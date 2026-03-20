import { Clerk } from '@clerk/clerk-js'
import './style.css'
import { askQuestion, clearHistory, initApp } from './app.js'

const clerk = new Clerk(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
await clerk.load()

const authWall = document.getElementById('auth-wall')

function showApp() {
  authWall.style.display = 'none'
  document.getElementById('app-root').style.display = ''
  document.body.style.visibility = 'visible'

  document.getElementById('sign-out-btn').addEventListener('click', async () => {
    await clerk.signOut()
    window.location.reload()
  })

  window.askQuestion = () => askQuestion(() => clerk.session?.getToken())
  window.clearHistory = clearHistory
  initApp()
}

if (clerk.user) {
  showApp()
} else {
  // Redirect to Clerk's hosted sign-in page; on return clerk.user will be set
  await clerk.redirectToSignIn({ redirectUrl: window.location.href })
}
