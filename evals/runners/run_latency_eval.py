# -*- coding: utf-8 -*-
"""L6 Latency/Performance Eval Runner."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.chat import chat_message, chat_start
from app.services.conversation_state import clear_conversation_state

PERF_MESSAGES = [
    ("knowledge", "什么是NPN传感器"),
    ("diagnosis", "PLC输入灯不亮"),
    ("short", "没有"),
    ("mixed", "解释PNP并排查故障"),
]

def run_latency_benchmark(iterations=3):
    results = {}
    total_start = time.time()

    for category, message in PERF_MESSAGES:
        times = []
        llm_counts = []
        for i in range(iterations):
            sid = f"perf-{category}-{i}"
            clear_conversation_state(sid)
            t0 = time.time()
            response = chat_message({"session_id": sid, "message": message, "context": {}})
            elapsed = (time.time() - t0) * 1000
            times.append(elapsed)
            llm_calls = response.get("llm_calls", response.get("conversation_state", {}).get("llm_calls", 0))
            if isinstance(llm_calls, (int, float)):
                llm_counts.append(llm_calls)
            clear_conversation_state(sid)

        avg_time = sum(times) / len(times) if times else 0
        avg_llm = sum(llm_counts) / len(llm_counts) if llm_counts else 0
        results[category] = {
            "avg_ms": round(avg_time, 1),
            "min_ms": round(min(times), 1) if times else 0,
            "max_ms": round(max(times), 1) if times else 0,
            "avg_llm_calls": round(avg_llm, 1),
            "iterations": iterations,
        }

    total_elapsed = (time.time() - total_start) * 1000
    return {
        "layer": "L6",
        "name": "Performance",
        "total_elapsed_ms": round(total_elapsed, 1),
        "results": results,
        "passed_cases": len(results),
        "failed_cases": 0,
        "total_cases": len(results),
    }

if __name__ == "__main__":
    report = run_latency_benchmark()
    print(json.dumps(report, ensure_ascii=False, indent=2))

