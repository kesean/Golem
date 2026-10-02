import { httpRouter } from "convex/server";
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

// Validate EvalRunPayload shape
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

    // Validate rulePassRate
    if (!run.summary.rulePassRate || typeof run.summary.rulePassRate !== "object") {
      return { valid: false, error: "Missing or invalid run.summary.rulePassRate" };
    }

    const ruleKeys = ["completed", "format", "productTag", "citations", "retrieval"];
    for (const key of ruleKeys) {
      if (!(key in run.summary.rulePassRate)) {
        return { valid: false, error: `Missing run.summary.rulePassRate.${key}` };
      }
    }

    // Validate regressions
    if (!validateRegressions(run.regressions)) {
      return { valid: false, error: "Invalid regressions" };
    }

    // Validate baselineRunId if present (should be string or null)
    if (run.baselineRunId !== null && run.baselineRunId !== undefined) {
      if (typeof run.baselineRunId !== "string") {
        return { valid: false, error: "Invalid run.baselineRunId" };
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
        if (typeof result.rules[key] !== "boolean") {
          return {
            valid: false,
            error: `results[${i}] rules.${key} is not boolean`,
          };
        }
      }

      // Validate judge if present
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
  handler: async (ctx, req) => {
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

    const { run: rawRun, results } = validation.payload!;

    // Process the run, removing null baselineRunId
    const run: any = { ...rawRun };
    if (run.baselineRunId === null) {
      delete run.baselineRunId;
    }

    // Call internal mutation to ingest the run
    const runId = await ctx.runMutation(internal.evalsIngest.ingestRun, {
      run,
      results,
    });

    return new Response(JSON.stringify({ runId }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
});

// GET /evals/baseline
http.route({
  path: "/evals/baseline",
  method: "GET",
  handler: async (ctx, req) => {
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
  },
});

export default http;
