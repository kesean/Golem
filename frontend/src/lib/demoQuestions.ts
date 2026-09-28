export type DemoQuestion = { label: string; question: string }

export const DEMO_QUESTIONS: DemoQuestion[] = [
  {
    label: 'Session token expiry',
    question: 'My Clerk session token keeps expiring and users get logged out. How do session tokens work and how do I fix this?',
  },
  {
    label: 'CORS error on API call',
    question: 'My browser blocks my fetch to the backend with a CORS error. What causes it and how do I debug it?',
  },
  {
    label: 'JWT template claims',
    question: 'How do I add custom claims to a Clerk JWT using a JWT template?',
  },
  {
    label: 'Streaming response cuts off',
    question: 'My server-sent events stream stops midway in production but works locally. What should I check?',
  },
  {
    label: '429 rate limit errors',
    question: 'My API returns 429 Too Many Requests intermittently. How do I diagnose and handle rate limiting?',
  },
]
