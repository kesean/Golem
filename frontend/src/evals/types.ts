export type RuleName = 'completed' | 'format' | 'productTag' | 'citations' | 'retrieval'
export type RuleResults = Record<RuleName, boolean>
export const RULE_NAMES: RuleName[] = ['completed', 'format', 'productTag', 'citations', 'retrieval']

export type Judge = { groundedness: number; coverage: number; keyPointsMissed: string[]; reason: string }

// Convex omits optional fields rather than storing null.
export type EvalResult = {
  _id: string
  runId: string
  caseId: string
  question: string
  response: string
  productTag?: string
  retrievedUrls: string[]
  rules: RuleResults
  judge?: Judge
  judgeError?: string
  latencyMs: number
  inputTokens: number
  outputTokens: number
  error?: string
}

export type EvalRun = {
  _id: string
  label: 'scheduled' | 'manual'
  gitSha: string
  gitRef: string
  appModel: string
  judgeModel: string
  casesVersion: number
  startedAt: number
  finishedAt: number
  status: 'completed' | 'errored'
  summary: {
    caseCount: number
    gradedCount: number
    errorCount: number
    meanScore: number
    rulePassRate: Record<RuleName, number>
  } & Record<string, unknown>
  regressions: unknown[]
}

export type RunDetail = {
  run: EvalRun
  results: EvalResult[]
  previous: { run: EvalRun; results: EvalResult[] } | null
}
