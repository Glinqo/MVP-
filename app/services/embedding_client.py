# -*- coding: utf-8 -*-
"""Small OpenAI-compatible embedding client for ability-node matching.

Configured via environment variables:
- EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
- LLM_API_KEY / LLM_BASE_URL may be reused for compatible gateways
"""
import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    base_url = os.environ.get("EMBEDDING_BASE_URL") or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
    return {
        "api_key": os.environ.get("EMBEDDING_API_KEY") or os.environ.get("LLM_API_KEY", ""),
        "base_url": base_url.rstrip("/"),
        "model": os.environ.get("EMBEDDING_MODEL", ""),
    }


def is_configured() -> bool:
    cfg = config()
    return bool(cfg["api_key"] and cfg["base_url"] and cfg["model"])


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def best_embedding_match(query: str, candidates: list, timeout: int = 30) -> dict | None:
    """Return the candidate with the highest embedding cosine similarity."""
    query = (query or "").strip()
    normalized = [_candidate_payload(candidate) for candidate in candidates]
    normalized = [item for item in normalized if item["id"] and item["text"]]
    if not query or not normalized:
        return None
    vectors = embed_texts([query] + [item["text"] for item in normalized], timeout=timeout)
    if len(vectors) != len(normalized) + 1:
        return None
    query_vector = vectors[0]
    best = None
    for item, vector in zip(normalized, vectors[1:]):
        score = cosine_similarity(query_vector, vector)
        if best is None or score > best["score"]:
            best = {**item, "score": score}
    return best


def embed_texts(texts: list[str], timeout: int = 30) -> list[list[float]]:
    """Embed texts with a cached OpenAI-compatible /embeddings endpoint."""
    cleaned = [str(text or "").strip() for text in texts]
    if not cleaned:
        return []
    cfg = config()
    if not is_configured():
        raise RuntimeError("embedding client is not configured")

    results: list[list[float] | None] = [None] * len(cleaned)
    pending: list[tuple[int, str]] = []
    for index, text in enumerate(cleaned):
        cached = _read_cache(cfg["model"], text)
        if cached is None:
            pending.append((index, text))
        else:
            results[index] = cached

    if pending:
        vectors = _request_embeddings([text for _, text in pending], cfg, timeout=timeout)
        if len(vectors) != len(pending):
            raise RuntimeError("embedding response length mismatch")
        for (index, text), vector in zip(pending, vectors):
            results[index] = vector
            _write_cache(cfg["model"], text, vector)

    return [vector or [] for vector in results]


def _request_embeddings(texts: list[str], cfg: dict, timeout: int) -> list[list[float]]:
    url = cfg["base_url"] + "/embeddings"
    request = urllib.request.Request(
        url,
        data=json.dumps({"model": cfg["model"], "input": texts}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"embedding request failed: {exc}") from exc

    rows = payload.get("data", [])
    rows = sorted(rows, key=lambda item: item.get("index", 0))
    return [list(map(float, row.get("embedding", []))) for row in rows]


def _candidate_payload(candidate) -> dict:
    if isinstance(candidate, tuple) and len(candidate) >= 2:
        return {"id": str(candidate[0]), "text": str(candidate[1]), "candidate": candidate}
    if isinstance(candidate, dict):
        text = " ".join([
            str(candidate.get("id") or ""),
            str(candidate.get("name") or candidate.get("label") or ""),
            str(candidate.get("description") or ""),
            " ".join(str(item) for item in candidate.get("related_knowledge", []) or []),
            " ".join(str(item) for item in candidate.get("common_errors", []) or []),
        ])
        return {"id": str(candidate.get("id") or ""), "text": text.strip(), "candidate": candidate}
    return {"id": "", "text": "", "candidate": candidate}


def _cache_enabled() -> bool:
    return os.environ.get("EMBEDDING_CACHE", "1").lower() not in {"0", "false", "no"}


def _cache_dir() -> Path:
    return Path(os.environ.get("EMBEDDING_CACHE_DIR", ROOT / "data" / "evidence" / "embedding_cache"))


def _cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}|{text}".encode("utf-8")).hexdigest()


def _read_cache(model: str, text: str) -> list[float] | None:
    if not _cache_enabled():
        return None
    path = _cache_dir() / f"{_cache_key(model, text)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [float(value) for value in payload.get("embedding", [])]
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_cache(model: str, text: str, vector: list[float]) -> None:
    if not _cache_enabled():
        return
    path = _cache_dir() / f"{_cache_key(model, text)}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model, "embedding": vector}), encoding="utf-8")
    except OSError:
        return
