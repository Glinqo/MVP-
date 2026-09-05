"""
向量索引模块 —— 基于 text2vec-base-chinese + FAISS 的轻量 RAG 检索。

架构:
  离线构建: scripts/build_vector_index.py 生成 faiss.index + documents.json
  运行时:   加载索引 → encode query → 向量召回 top-k

依赖: sentence-transformers, faiss-cpu
"""

import json
import logging
from pathlib import Path
from functools import lru_cache

import numpy as np

from .data_loader import load_data

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "knowledge" / "vector_index"
INDEX_PATH = INDEX_DIR / "faiss.index"
DOCS_PATH = INDEX_DIR / "documents.json"

MODEL_NAME = "shibing624/text2vec-base-chinese"
EMBEDDING_DIM = 768

# ---------------------------------------------------------------------------
# 文档文本构造（决定向量检索的质量）
# ---------------------------------------------------------------------------


def _knowledge_doc_text(item: dict) -> str:
    """将一条知识条目拼成一段可供 embedding 的文本。"""
    parts = []
    for key in ("topic", "content", "job_task"):
        val = item.get(key, "")
        if val:
            parts.append(str(val))
    for key in ("common_errors",):
        val = item.get(key)
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
    return " ".join(parts)


def _pattern_doc_text(pattern: dict) -> str:
    """将一条问题模式拼成可供 embedding 的文本。"""
    parts = []
    for key in ("title", "typical_symptom"):
        val = pattern.get(key, "")
        if val:
            parts.append(str(val))
    return " ".join(parts)


def _build_document_list():
    """从 load_data() 中提取所有可向量化的文档。"""
    data = load_data()
    docs = []

    for item in data["knowledge"]:
        docs.append({
            "doc_id": item.get("id", ""),
            "doc_type": "knowledge",
            "text": _knowledge_doc_text(item),
        })

    for pattern in data["problem_patterns"]:
        docs.append({
            "doc_id": pattern.get("id", ""),
            "doc_type": "pattern",
            "text": _pattern_doc_text(pattern),
        })

    return docs


# ---------------------------------------------------------------------------
# 向量索引管理
# ---------------------------------------------------------------------------

_vector_index = None       # faiss.IndexFlatIP 实例
_model = None              # SentenceTransformer 实例
_documents: list[dict] = []# 文档列表


def _get_model():
    """懒加载 embedding 模型（优先本地缓存，避免网络连接超时）。"""
    global _model
    if _model is None:
        try:
            import os

            # 优先使用国内镜像
            if "HF_ENDPOINT" not in os.environ:
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

            from sentence_transformers import SentenceTransformer

            # 先尝试纯离线加载（已构建过索引则模型一定在本地缓存中）
            try:
                _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
                logger.info("Vector model loaded (offline): %s", MODEL_NAME)
            except Exception:
                logger.info("Model not cached locally, attempting download via mirror...")
                _model = SentenceTransformer(MODEL_NAME, local_files_only=False)
                logger.info("Vector model loaded (online): %s", MODEL_NAME)
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装，请执行: pip install sentence-transformers"
            )
    return _model


def _load_or_build_index():
    """加载 FAISS 索引和文档列表。磁盘存在则加载，否则实时构建。"""
    global _vector_index, _documents

    if _vector_index is not None:
        return

    import faiss

    if INDEX_PATH.exists() and DOCS_PATH.exists():
        logger.info("Loading FAISS index from disk: %s", INDEX_PATH)
        _vector_index = faiss.read_index(str(INDEX_PATH))
        _documents = json.loads(DOCS_PATH.read_text(encoding="utf-8"))
    else:
        logger.info("Vector index not found, building in-memory (one-time)...")
        _build_in_memory_index()


def _build_in_memory_index():
    """纯内存构建索引（不写磁盘，用于首次启动或脚本未运行时）。"""
    global _vector_index, _documents

    import faiss

    model = _get_model()
    docs = _build_document_list()
    texts = [d["text"] for d in docs]

    logger.info("Encoding %d documents...", len(texts))
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    _vector_index = faiss.IndexFlatIP(EMBEDDING_DIM)
    _vector_index.add(embeddings.astype(np.float32))
    _documents = docs
    logger.info("In-memory vector index ready: %d docs", len(docs))


def get_index():
    """获取已初始化的 (faiss_index, documents) 元组。"""
    _load_or_build_index()
    return _vector_index, _documents


# ---------------------------------------------------------------------------
# 检索接口
# ---------------------------------------------------------------------------


def vector_search(query: str, top_k: int = 20) -> list[dict]:
    """向量语义召回 top_k 条文档。

    Returns:
        [{doc_id, doc_type, text, score (0~1)}, ...]
    """
    index, docs = get_index()
    model = _get_model()

    query_vec = model.encode([query], normalize_embeddings=True)
    scores, indices = index.search(query_vec.astype(np.float32), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(docs) or score <= 0:
            continue
        doc = docs[idx]
        results.append({
            "doc_id": doc["doc_id"],
            "doc_type": doc["doc_type"],
            "text": doc["text"],
            "score": float(score),
        })

    return results


def vector_available() -> bool:
    """检测向量检索是否可用（依赖是否安装 + 索引是否存在或可构建）。"""
    try:
        import sentence_transformers  # noqa: F401
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False
