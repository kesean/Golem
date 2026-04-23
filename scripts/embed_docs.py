#!/usr/bin/env python3
"""
embed_docs.py — Embed Clerk and MDN docs into Qdrant Cloud.

Re-running is safe — chunks upserted by deterministic ID.

Usage:
    python scripts/embed_docs.py

Required env vars (loaded from .env):
    QDRANT_URL, QDRANT_API_KEY, VOYAGE_API_KEY

Optional:
    GITHUB_TOKEN  — raises GitHub API rate limit from 60 to 5000 req/hr
"""

import os
import sys
import uuid
import base64
import hashlib
import logging

import httpx
import tiktoken
import voyageai
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── Required env vars ─────────────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# ── Constants ─────────────────────────────────────────────────────────────────

COLLECTION = "dev_support_docs"
CHUNK_SIZE = 500
CHUNK_TOKENS = CHUNK_SIZE   # alias used by tests and external callers
OVERLAP = 50
VOYAGE_BATCH = 128
VECTOR_DIM = 1024    # voyage-3.5-lite actual output dimension

# ── Clerk file list ───────────────────────────────────────────────────────────

CLERK_FILES = [
    "docs/guides/how-clerk-works/overview.mdx",
    "docs/guides/sessions/session-tokens.mdx",
    "docs/guides/sessions/jwt-templates.mdx",
    "docs/reference/backend/overview.mdx",
    "docs/reference/backend/authenticate-request.mdx",
    "docs/reference/backend/verify-token.mdx",
]

# ── MDN file list ─────────────────────────────────────────────────────────────

MDN_FILES = [
    "files/en-us/web/api/fetch_api/index.md",
    "files/en-us/web/api/fetch_api/using_fetch/index.md",
    "files/en-us/web/api/headers/index.md",
    "files/en-us/web/api/request/index.md",
    "files/en-us/web/api/response/index.md",
    "files/en-us/web/http/reference/status/index.md",
    "files/en-us/web/http/reference/status/200/index.md",
    "files/en-us/web/http/reference/status/201/index.md",
    "files/en-us/web/http/reference/status/400/index.md",
    "files/en-us/web/http/reference/status/401/index.md",
    "files/en-us/web/http/reference/status/403/index.md",
    "files/en-us/web/http/reference/status/404/index.md",
    "files/en-us/web/http/reference/status/429/index.md",
    "files/en-us/web/http/reference/status/500/index.md",
    "files/en-us/web/http/guides/cors/index.md",
]

# ── Source registry ───────────────────────────────────────────────────────────

SOURCES = [
    {"name": "Clerk", "owner": "clerk", "repo": "clerk-docs", "branch": "main", "files": CLERK_FILES},
    {"name": "MDN",   "owner": "mdn",   "repo": "content",    "branch": "main", "files": MDN_FILES},
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def fetch_file(owner: str, repo: str, path: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = httpx.get(url, headers=github_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") != "base64":
        raise ValueError(f"Unexpected encoding for {path}: {data.get('encoding')}")
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def chunk_text(text: str, enc: tiktoken.Encoding | None = None) -> list[str]:
    if enc is None:
        enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += CHUNK_SIZE - OVERLAP
    return chunks


def chunk_id(repo_path: str, chunk_index: int) -> str:
    """Deterministic UUID ID — re-runs upsert rather than duplicate.

    Qdrant requires point IDs to be unsigned 64-bit integers or UUID strings.
    We derive a stable UUID from the first 32 hex chars of the SHA-256 digest.
    """
    digest = hashlib.sha256(f"{repo_path}:{chunk_index}".encode()).hexdigest()
    return str(uuid.UUID(digest[:32]))


def check_file_exists(owner: str, repo: str, path: str) -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = httpx.get(url, headers=github_headers(), timeout=15)
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    raise RuntimeError(f"GitHub API returned {resp.status_code} for {path} — set GITHUB_TOKEN to avoid rate limits")


def validate_sources() -> None:
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN not set — validation limited to 60 req/hr; set it to avoid rate limit errors")
    failed = []
    for source in SOURCES:
        for path in source["files"]:
            if not check_file_exists(source["owner"], source["repo"], path):
                failed.append(f"{source['name']}: {path}")
    if failed:
        logging.error("Path validation failed — %d file(s) not found:", len(failed))
        for f in failed:
            logging.error("  404 %s", f)
        sys.exit(1)
    total = sum(len(s["files"]) for s in SOURCES)
    logging.info("All %d source paths validated OK", total)


def embed_in_batches(texts: list[str], voyage: voyageai.Client) -> list[list[float]]:
    vectors = []
    for i in range(0, len(texts), VOYAGE_BATCH):
        batch = texts[i : i + VOYAGE_BATCH]
        result = voyage.embed(batch, model="voyage-3.5-lite", input_type="document")
        vectors.extend(result.embeddings)
    return vectors


def ensure_collection(qdrant: QdrantClient) -> None:
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION in existing:
        info = qdrant.get_collection(COLLECTION)
        actual_dim = info.config.params.vectors.size
        if actual_dim != VECTOR_DIM:
            logging.info("Collection '%s' has wrong dimension (%d vs %d) — recreating", COLLECTION, actual_dim, VECTOR_DIM)
            qdrant.delete_collection(COLLECTION)
        else:
            logging.info("Collection '%s' already exists — upserting", COLLECTION)
            return
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    logging.info("Created collection '%s'", COLLECTION)


# ── Main ──────────────────────────────────────────────────────────────────────


def main(validate_only: bool = False) -> None:
    validate_sources()
    if validate_only:
        return

    missing = [k for k, v in {"QDRANT_URL": QDRANT_URL, "QDRANT_API_KEY": QDRANT_API_KEY, "VOYAGE_API_KEY": VOYAGE_API_KEY}.items() if not v]
    if missing:
        logging.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)

    enc = tiktoken.get_encoding("cl100k_base")
    voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    ensure_collection(qdrant_client)

    for source in SOURCES:
        name = source["name"]
        owner = source["owner"]
        repo = source["repo"]
        file_list = source["files"]

        all_chunks: list[str] = []
        all_meta: list[dict] = []

        for path in file_list:
            try:
                content = fetch_file(owner, repo, path)
            except Exception as e:
                logging.error("  FAILED %s — fetch error: %s", path, e)
                raise

            chunks = chunk_text(content, enc)
            github_url = f"https://github.com/{owner}/{repo}/blob/main/{path}"
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_meta.append({
                    "source": name,
                    "repo_path": path,
                    "github_url": github_url,
                    "chunk_index": i,
                    "text": chunk,
                })

        if not all_chunks:
            logging.warning("%s: no chunks collected — check file paths above", name)
            continue

        logging.info("%s: %d files, %d chunks — embedding...", name, len(file_list), len(all_chunks))
        vectors = embed_in_batches(all_chunks, voyage_client)

        points = [
            PointStruct(
                id=chunk_id(meta["repo_path"], meta["chunk_index"]),
                vector=vector,
                payload=meta,
            )
            for meta, vector in zip(all_meta, vectors)
        ]
        qdrant_client.upsert(collection_name=COLLECTION, points=points)
        logging.info("%s: upserted %d points", name, len(points))

    logging.info("Done.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true", help="Check source paths exist without embedding")
    args = parser.parse_args()
    try:
        main(validate_only=args.validate_only)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.error("embed_docs failed: %s", e)
        sys.exit(1)
