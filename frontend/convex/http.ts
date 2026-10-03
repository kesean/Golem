import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";

const http = httpRouter();

// Constant-time string comparison for bearer token
function constantTimeCompare(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

// Validate bearer token
function validateBearer(authHeader: string | null): boolean {
  const secret = process.env.EVAL_INGEST_SECRET;
  if (!secret || !authHeader) {
    return false;
  }

  const parts = authHeader.split(" ");
  if (parts.length !== 2 || parts[0] !== "Bearer") {
    return false;
  }

  return constantTimeCompare(parts[1], secret);
}

// Validate regression objects
function validateRegressions(regressions: any): boolean {
  if (!Array.isArray(regressions)) {
    return false;
  }

  for (const regression of regressions) {
    if (!regression || typeof regression !== "object") {
      return false;
    }

    const kind = regression.kind;
    if (
      ![
        "meanScoreDrop",
        "ruleFlip",
        "caseScoreDrop",
        "errorRate",
        "recentBestDrop",
      ].includes(kind)
    ) {
      return false;
    }

    // Validate based on kind
    switch (kind) {
      case "meanScoreDrop":
        if (
          typeof regression.baseline !== "number" ||
          typeof regression.current !== "number"
        ) {
          return false;
        }
        break;
      case "ruleFlip":
        if (
          typeof regression.caseId !== "string" ||
          ![
            "completed",
            "format",
            "productTag",
            "citations",
            "retrieval",
          ].includes(regression.rule)
        ) {
          return false;
        }
        break;
      case "caseScoreDrop":
        if (
          typeof regression.caseId !== "string" ||
          typeof regression.baseline !== "number" ||
          typeof regression.current !== "number"
        ) {
          return false;
        }
        break;
      case "errorRate":
        if (
          typeof regression.errorCount !== "number" ||
          typeof regression.caseCount !== "number"
        ) {
          return false;
        }
        break;
      case "recentBestDrop":
        if (
          typeof regression.recentBest !== "number" ||
          typeof regression.current !== "number"
        ) {
          return false;
        }
        break;
    }
  }

  return true;
}

// Type validators
function isFiniteNumber(n: any): boolean {
  return typeof n === "number" && Number.isFinite(n);
}

function isString(s: any): boolean {
  return typeof s === "string";
}

function isBoolean(b: any): boolean {
  return typeof b === "boolean";
}

function isStringArray(arr: any): boolean {
  return Array.isArray(arr) && arr.every((item) => typeof item === "string");
}

// Validate EvalRunPayload shape with comprehensive type checking
function validatePayload(body: any): {
  valid: boolean;
  error?: string;
  payload?: { run: any; results: any };
} {
  try {
    if (!body || typeof body !== "object") {
      return { valid: false, error: "Invalid JSON body" };
    }

    const { run, results } = body;

    if (!run || typeof run !== "object") {
      return { valid: false, error: "Missing or invalid run object" };
    }

    if (!Array.isArray(results)) {
      return { valid: false, error: "Missing or invalid results array" };
    }

    // Validate run fields
    const requiredRunFields = [
      "label",
      "gitSha",
      "gitRef",
      "appModel",
      "judgeModel",
      "casesVersion",
      "startedAt",
      "finishedAt",
      "status",
      "summary",
      "regressions",
    ];

    for (const field of requiredRunFields) {
      if (!(field in run)) {
        return { valid: false, error: `Missing run.${field}` };
      }
    }

    // Validate label
    if (!["scheduled", "manual"].includes(run.label)) {
      return { valid: false, error: "Invalid run.label" };
    }

    // Validate status
    if (!["completed", "errored"].includes(run.status)) {
      return { valid: false, error: "Invalid run.status" };
    }

    // Validate string fields
    if (!isString(run.gitSha)) {
      return { valid: false, error: "Invalid run.gitSha type" };
    }
    if (!isString(run.gitRef)) {
      return { valid: false, error: "Invalid run.gitRef type" };
    }
    if (!isString(run.appModel)) {
      return { valid: false, error: "Invalid run.appModel type" };
    }
    if (!isString(run.judgeModel)) {
      return { valid: false, error: "Invalid run.judgeModel type" };
    }

    // Validate numeric fields
    if (!isFiniteNumber(run.casesVersion)) {
      return { valid: false, error: "Invalid run.casesVersion type" };
    }
    if (!isFiniteNumber(run.startedAt)) {
      return { valid: false, error: "Invalid run.startedAt type" };
    }
    if (!isFiniteNumber(run.finishedAt)) {
      return { valid: false, error: "Invalid run.finishedAt type" };
    }

    // Validate summary
    if (!run.summary || typeof run.summary !== "object") {
      return { valid: false, error: "Missing or invalid run.summary" };
    }

    const summaryFields = [
      "caseCount",
      "gradedCount",
      "errorCount",
      "meanGroundedness",
      "meanCoverage",
      "meanScore",
      "rulePassRate",
      "p50LatencyMs",
      "p95LatencyMs",
      "totalInputTokens",
      "totalOutputTokens",
    ];

    for (const field of summaryFields) {
      if (!(field in run.summary)) {
        return { valid: false, error: `Missing run.summary.${field}` };
      }
    }

    // Validate summary numeric fields
    const numericSummaryFields = [
      "caseCount",
      "gradedCount",
      "errorCount",
      "meanGroundedness",
      "meanCoverage",
      "meanScore",
      "p50LatencyMs",
      "p95LatencyMs",
      "totalInputTokens",
      "totalOutputTokens",
    ];

    for (const field of numericSummaryFields) {
      if (!isFiniteNumber(run.summary[field])) {
        return { valid: false, error: `Invalid run.summary.${field} type` };
      }
    }

    // Validate rulePassRate
    if (!run.summary.rulePassRate || typeof run.summary.rulePassRate !== "object") {
      return { valid: false, error: "Missing or invalid run.summary.rulePassRate" };
    }

    const ruleKeys = ["completed", "format", "productTag", "citations", "retrieval"];
    for (const key of ruleKeys) {
      if (!(key in run.summary.rulePassRate)) {
        return { valid: false, error: `Missing run.summary.rulePassRate.${key}` };
      }
      if (!isFiniteNumber(run.summary.rulePassRate[key])) {
        return {
          valid: false,
          error: `Invalid run.summary.rulePassRate.${key} type`,
        };
      }
    }

    // Validate regressions
    if (!validateRegressions(run.regressions)) {
      return { valid: false, error: "Invalid regressions" };
    }

    // Validate baselineRunId if present (should be string or null)
    if (run.baselineRunId !== null && run.baselineRunId !== undefined) {
      if (!isString(run.baselineRunId)) {
        return { valid: false, error: "Invalid run.baselineRunId type" };
      }
    }

    // Validate results
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      if (!result || typeof result !== "object") {
        return { valid: false, error: `results[${i}] is not an object` };
      }

      const resultFields = [
        "caseId",
        "question",
        "response",
        "retrievedUrls",
        "rules",
        "latencyMs",
        "inputTokens",
        "outputTokens",
      ];

      for (const field of resultFields) {
        if (!(field in result)) {
          return { valid: false, error: `results[${i}] missing ${field}` };
        }
      }

      // Validate string fields in result
      if (!isString(result.caseId)) {
        return { valid: false, error: `results[${i}] caseId is not a string` };
      }
      if (!isString(result.question)) {
        return { valid: false, error: `results[${i}] question is not a string` };
      }
      if (!isString(result.response)) {
        return { valid: false, error: `results[${i}] response is not a string` };
      }

      // Validate retrievedUrls is array of strings
      if (!isStringArray(result.retrievedUrls)) {
        return {
          valid: false,
          error: `results[${i}] retrievedUrls is not an array of strings`,
        };
      }

      // Validate numeric fields in result
      if (!isFiniteNumber(result.latencyMs)) {
        return { valid: false, error: `results[${i}] latencyMs is not a number` };
      }
      if (!isFiniteNumber(result.inputTokens)) {
        return { valid: false, error: `results[${i}] inputTokens is not a number` };
      }
      if (!isFiniteNumber(result.outputTokens)) {
        return { valid: false, error: `results[${i}] outputTokens is not a number` };
      }

      // Validate rules
      if (!result.rules || typeof result.rules !== "object") {
        return {
          valid: false,
          error: `results[${i}] has invalid rules`,
        };
      }

      for (const key of ruleKeys) {
        if (!(key in result.rules)) {
          return {
            valid: false,
            error: `results[${i}] rules missing ${key}`,
          };
        }
        if (!isBoolean(result.rules[key])) {
          return {
            valid: false,
            error: `results[${i}] rules.${key} is not a boolean`,
          };
        }
      }

      // Validate productTag if present (should be string or null)
      if (result.productTag !== null && result.productTag !== undefined) {
        if (!isString(result.productTag)) {
          return {
            valid: false,
            error: `results[${i}] productTag is not a string`,
          };
        }
      }

      // Validate judge if present (should be object or null)
      if (result.judge !== null && result.judge !== undefined) {
        if (typeof result.judge !== "object") {
          return {
            valid: false,
            error: `results[${i}] judge is not an object`,
          };
        }
        const judgeFields = ["groundedness", "coverage", "keyPointsMissed", "reason"];
        for (const field of judgeFields) {
          if (!(field in result.judge)) {
            return {
              valid: false,
              error: `results[${i}] judge missing ${field}`,
            };
          }
        }
        // Validate judge numeric scores
        if (!isFiniteNumber(result.judge.groundedness)) {
          return {
            valid: false,
            error: `results[${i}] judge.groundedness is not a number`,
          };
        }
        if (!isFiniteNumber(result.judge.coverage)) {
          return {
            valid: false,
            error: `results[${i}] judge.coverage is not a number`,
          };
        }
        if (!isStringArray(result.judge.keyPointsMissed)) {
          return {
            valid: false,
            error: `results[${i}] judge.keyPointsMissed is not an array of strings`,
          };
        }
        if (!isString(result.judge.reason)) {
          return {
            valid: false,
            error: `results[${i}] judge.reason is not a string`,
          };
        }
      }

      // Validate judgeError if present (should be string or null)
      if (result.judgeError !== null && result.judgeError !== undefined) {
        if (!isString(result.judgeError)) {
          return {
            valid: false,
            error: `results[${i}] judgeError is not a string`,
          };
        }
      }

      // Validate error if present (should be string or null)
      if (result.error !== null && result.error !== undefined) {
        if (!isString(result.error)) {
          return {
            valid: false,
            error: `results[${i}] error is not a string`,
          };
        }
      }
    }

    return { valid: true, payload: { run, results } };
  } catch (err) {
    return { valid: false, error: "Invalid JSON body" };
  }
}

// POST /evals/runs
http.route({
  path: "/evals/runs",
  method: "POST",
  handler: httpAction(async (ctx, req) => {
    // Validate bearer token
    const authHeader = req.headers.get("Authorization");
    if (!validateBearer(authHeader)) {
      return new Response(JSON.stringify({}), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Parse and validate body
    let body: any;
    try {
      body = await req.json();
    } catch {
      return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const validation = validatePayload(body);
    if (!validation.valid) {
      return new Response(JSON.stringify({ error: validation.error }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const { run: rawRun, results: rawResults } = validation.payload!;

    // Normalize the run: remove null baselineRunId
    const run: any = { ...rawRun };
    if (run.baselineRunId === null) {
      delete run.baselineRunId;
    }

    // Normalize results: remove null optional fields
    const results = rawResults.map((result: any) => {
      const normalized: any = { ...result };
      if (normalized.productTag === null) {
        delete normalized.productTag;
      }
      if (normalized.judge === null) {
        delete normalized.judge;
      }
      if (normalized.judgeError === null) {
        delete normalized.judgeError;
      }
      if (normalized.error === null) {
        delete normalized.error;
      }
      return normalized;
    });

    // Call internal mutation to ingest the run with error handling
    try {
      const runId = await ctx.runMutation(internal.evalsIngest.ingestRun, {
        run,
        results,
      });

      return new Response(JSON.stringify({ runId }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isValidationError =
        (err instanceof Error && err.name === "ArgumentValidationError") ||
        message.includes("ArgumentValidationError") ||
        message.includes("Validator");
      if (isValidationError) {
        return new Response(JSON.stringify({ error: message }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      }
      console.error("evals ingest failed", err);
      return new Response(JSON.stringify({ error: "Internal error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  }),
});

// GET /evals/baseline
http.route({
  path: "/evals/baseline",
  method: "GET",
  handler: httpAction(async (ctx, req) => {
    // Validate bearer token
    const authHeader = req.headers.get("Authorization");
    if (!validateBearer(authHeader)) {
      return new Response(JSON.stringify({}), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Call internal query to get latest scheduled run
    const baseline = await ctx.runQuery(internal.evalsIngest.latestScheduled);

    return new Response(JSON.stringify(baseline), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export default http;
