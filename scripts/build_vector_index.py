"""
离线构建向量索引脚本。

用法:
    python scripts/build_vector_index.py

产物:
    knowledge/vector_index/faiss.index      —— FAISS 向量索引
    knowledge/vector_index/documents.json   —— 文档 ID/类型/文本映射

首次运行时 sentence-transformers 会自动下载 text2vec-base-chinese 模型到本地缓存。
"""

import json
import sys
from pathlib import Path

import numpy as np

# 把项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.data_loader import load_data
from sentence_transformers import SentenceTransformer
import faiss

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

MODEL_NAME = "shibing624/text2vec-base-chinese"
EMBEDDING_DIM = 768
INDEX_DIR = ROOT / "knowledge" / "vector_index"

# ---------------------------------------------------------------------------
# 文档文本构造（与 vector_index.py 保持一致）
# ---------------------------------------------------------------------------


def knowledge_doc_text(item: dict) -> str:
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


def pattern_doc_text(pattern: dict) -> str:
    parts = []
    for key in ("title", "typical_symptom"):
        val = pattern.get(key, "")
        if val:
            parts.append(str(val))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("  向量索引构建工具")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1/4] 加载知识库数据...")
    data = load_data()
    knowledge_count = len(data["knowledge"])
    pattern_count = len(data["problem_patterns"])
    print(f"  知识条目: {knowledge_count} 条")
    print(f"  问题模式: {pattern_count} 条")

    # 2. 构建文档列表
    print("\n[2/4] 构建文档文本...")
    documents = []

    for item in data["knowledge"]:
        documents.append({
            "doc_id": item.get("id", ""),
            "doc_type": "knowledge",
            "text": knowledge_doc_text(item),
        })

    for pattern in data["problem_patterns"]:
        documents.append({
            "doc_id": pattern.get("id", ""),
            "doc_type": "pattern",
            "text": pattern_doc_text(pattern),
        })

    print(f"  共 {len(documents)} 条文档")
    texts = [d["text"] for d in documents]

    # 3. 加载模型并编码
    print(f"\n[3/4] 加载 embedding 模型: {MODEL_NAME}")
    print("  (首次运行会自动下载模型，约 400MB，请耐心等待...)")
    model = SentenceTransformer(MODEL_NAME)
    print("  模型加载完成，开始编码...")

    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    print(f"  编码完成: {embeddings.shape}")

    # 4. 构建 FAISS 索引并持久化
    print("\n[4/4] 构建 FAISS 索引并保存...")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings.astype(np.float32))

    faiss.write_index(index, str(INDEX_DIR / "faiss.index"))
    (INDEX_DIR / "documents.json").write_text(
        json.dumps(documents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  索引文件: {INDEX_DIR / 'faiss.index'}")
    print(f"  文档文件: {INDEX_DIR / 'documents.json'}")
    file_size = (INDEX_DIR / "faiss.index").stat().st_size
    print(f"  索引大小: {file_size / 1024:.1f} KB")
    print(f"  文档数量: {len(documents)}")
    print("\n" + "=" * 60)
    print("  向量索引构建完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
