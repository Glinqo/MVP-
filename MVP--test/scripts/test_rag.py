"""
RAG 向量检索效果测试脚本。

对比原始关键词检索 vs 向量混合检索，验证语义匹配能力。
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.retrieval import search_knowledge
from app.services.vector_index import vector_search, vector_available


def print_separator(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_results(results, method):
    print(f"\n  [{method}] 返回 {len(results)} 条结果：")
    for i, item in enumerate(results):
        print(f"  #{i + 1} [{item['id']}] {item['topic']}")
        print(f"       得分: {item['score']:.4f} | 原因: {item['match_reason'][:60]}")
        content_preview = (item.get("content") or "")[:80]
        print(f"       内容: {content_preview}...")


def test_query(query, description):
    print_separator(description)
    print(f"  Query: \"{query}\"")

    t0 = time.time()
    results = search_knowledge(query, limit=5)
    elapsed = (time.time() - t0) * 1000

    print_results(results, f"混合检索 ({elapsed:.0f}ms)")

    if results:
        print(f"\n  向量可用: {vector_available()}")


# ===================================================================
# 测试用例：语义相近但字面不同的查询
# ===================================================================

def main():
    print("=" * 70)
    print("  RAG 向量检索效果测试")
    print("=" * 70)
    print(f"  向量模块可用: {vector_available()}")

    # ---- 测试1: 口语化表达 vs 专业术语 ----
    test_query(
        "传感器没电了怎么办",
        "测试1: 口语化 '没电' → 应匹配 DC24V 供电相关条目",
    )

    # ---- 测试2: 同义表达 ----
    test_query(
        "怎么判断传感器有没有坏",
        "测试2: '判断传感器好坏' → 应匹配 传感器输出端电压检查",
    )

    # ---- 测试3: 近义表达 ----
    test_query(
        "棕色线和蓝色线接反了",
        "测试3: '线色接反' → 应匹配 NPN/PNP 接线相关条目",
    )

    # ---- 测试4: 场景描述 ----
    test_query(
        "我的气缸动不了但是程序好像是对的",
        "测试4: 场景描述 → 应匹配 气缸不动作分层排查",
    )

    # ---- 测试5: 模糊表达 ----
    test_query(
        "设备好像不太对，灯是亮的但软件没反应",
        "测试5: 模糊描述 → 应匹配 PLC输入灯亮但在线监控不对",
    )

    # ---- 测试6: 精确术语（验证关键词不退化） ----
    test_query(
        "NPN传感器和PNP传感器的区别是什么",
        "测试6: 精确术语 'NPN/PNP' → 应保持精确匹配能力",
    )

    # ---- 测试7: 跨知识域 ----
    test_query(
        "安全规范方面需要注意什么",
        "测试7: '安全规范' → 应匹配 断电确认、急停等安全条目",
    )

    print_separator("测试完成")
    print("\n  对比要点：")
    print("  - 语义相近的查询是否召回正确条目")
    print("  - 排序是否合理")
    print("  - 精确术语查询是否不受影响")


if __name__ == "__main__":
    main()
