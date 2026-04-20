"""api_lookup.py — Fetch live data from Clerk or Anthropic APIs.

Hard URL allowlist prevents Claude from instructing arbitrary URL fetches.
All credentials loaded from env vars. Never raises — always returns a string.
"""

import json
import os

import httpx

# ---------------------------------------------------------------------------
# Allowlists
# ---------------------------------------------------------------------------

CLERK_ENDPOINTS = {
    "errors": "https://api.clerk.com/v1/errors",
    "jwks":   "https://{clerk_domain}/.well-known/jwks.json",
}

ANTHROPIC_ENDPOINTS = {
    "models": "https://api.anthropic.com/v1/models",
}

_TIMEOUT = 10.0  # seconds


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch(service: str, endpoint: str, params: dict | None = None) -> str:
    """Fetch live data from Clerk or Anthropic APIs.

    service: 'clerk' | 'anthropic'
    endpoint: key in the corresponding endpoint allowlist
    params: optional query parameters passed to httpx.get

    Returns a formatted string on success, plain error string on failure.
    Never raises — always returns a string.
    """
    try:
        if service == "clerk":
            return _fetch_clerk(endpoint, params)
        elif service == "anthropic":
            return _fetch_anthropic(endpoint, params)
        else:
            return f"Error: unknown service '{service}'. Must be 'clerk' or 'anthropic'."
    except Exception as exc:  # belt-and-suspenders — specific handlers below should catch first
        return f"Error: unexpected failure — {exc}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_clerk(endpoint: str, params: dict | None) -> str:
    """Resolve and call a Clerk endpoint from the allowlist."""
    if endpoint not in CLERK_ENDPOINTS:
        return (
            f"Error: unknown Clerk endpoint '{endpoint}'. "
            f"Allowed endpoints: {list(CLERK_ENDPOINTS.keys())}."
        )

    secret_key = os.getenv("CLERK_SECRET_KEY")
    if not secret_key:
        return "Error: missing CLERK_SECRET_KEY environment variable."

    url = CLERK_ENDPOINTS[endpoint]

    # Substitute {clerk_domain} if present
    if "{clerk_domain}" in url:
        clerk_domain = os.getenv("CLERK_DOMAIN")
        if not clerk_domain:
            return "Error: missing CLERK_DOMAIN environment variable (required for JWKS URL)."
        url = url.replace("{clerk_domain}", clerk_domain)

    return _do_get(url, headers={"Authorization": f"Bearer {secret_key}"}, params=params)


def _fetch_anthropic(endpoint: str, params: dict | None) -> str:
    """Resolve and call an Anthropic endpoint from the allowlist."""
    if endpoint not in ANTHROPIC_ENDPOINTS:
        return (
            f"Error: unknown Anthropic endpoint '{endpoint}'. "
            f"Allowed endpoints: {list(ANTHROPIC_ENDPOINTS.keys())}."
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: missing ANTHROPIC_API_KEY environment variable."

    url = ANTHROPIC_ENDPOINTS[endpoint]

    return _do_get(
        url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        params=params,
    )


def _do_get(url: str, headers: dict, params: dict | None) -> str:
    """Execute an httpx GET and return a formatted string or error string."""
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data, indent=2)
    except httpx.TimeoutException as exc:
        return f"Error: request timed out — {exc}"
    except httpx.HTTPStatusError as exc:
        return f"Error: HTTP {exc.response.status_code} from {url}"
    except Exception as exc:
        return f"Error: request failed — {exc}"
