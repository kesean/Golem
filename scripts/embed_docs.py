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

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# ── Constants ─────────────────────────────────────────────────────────────────

COLLECTION = "dev_support_docs"
CHUNK_SIZE = 500
OVERLAP = 50
VOYAGE_BATCH = 128
VECTOR_DIM = 512     # voyage-3.5-lite default

# ── Clerk file list ───────────────────────────────────────────────────────────

CLERK_FILES = [
    "docs/authentication/overview.mdx",
    "docs/authentication/session-tokens.mdx",
    "docs/authentication/jwt-templates.mdx",
    "docs/backend-requests/overview.mdx",
    "docs/backend-requests/handling.mdx",
    "docs/errors/overview.mdx",
]

# ── MDN file list ─────────────────────────────────────────────────────────────

MDN_FILES = [
    "files/en-us/web/api/fetch_api/index.md",
    "files/en-us/web/api/fetch_api/using_fetch/index.md",
    "files/en-us/web/api/headers/index.md",
    "files/en-us/web/api/request/index.md",
    "files/en-us/web/api/response/index.md",
    "files/en-us/web/http/status/index.md",
    "files/en-us/web/http/status/200/index.md",
    "files/en-us/web/http/status/201/index.md",
    "files/en-us/web/http/status/400/index.md",
    "files/en-us/web/http/status/401/index.md",
    "files/en-us/web/http/status/403/index.md",
    "files/en-us/web/http/status/404/index.md",
    "files/en-us/web/http/status/429/index.md",
    "files/en-us/web/http/status/500/index.md",
    "files/en-us/web/http/cors/index.md",
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


def chunk_text(text: str, enc: tiktoken.Encoding) -> list[str]:
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
    """Deterministic SHA-256 ID — re-runs upsert rather than duplicate."""
    return hashlib.sha256(f"{repo_path}:{chunk_index}".encode()).hexdigest()


def embed_in_batches(texts: list[str], voyage: voyageai.Client) -> list[list[float]]:
    vectors = []
    for i in range(0, len(texts), VOYAGE_BATCH):
        batch = texts[i : i + VOYAGE_BATCH]
        result = voyage.embed(batch, model="voyage-3.5-lite", input_type="document")
        vectors.extend(result.embeddings)
    return vectors


def ensure_collection(qdrant: QdrantClient) -> None:
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logging.info("Created collection '%s'", COLLECTION)
    else:
        logging.info("Collection '%s' already exists — upserting", COLLECTION)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
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
                logging.error("  SKIP %s — fetch failed: %s", path, e)
                continue

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
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.error("embed_docs failed: %s", e)
        sys.exit(1)
