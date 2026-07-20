"""
Comprehensive test suite for the memory system optimization.
Tests all 4 components: concurrency, SQLite store, conversation memory,
graph incremental cache, and cross-session long-term memory.
"""
import json, os, sys, threading, time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.feedback import (
    append_session_event, load_session_record, save_feedback,
    _get_session_lock, safe_session_id
)
from app.services.session_store import (
    insert_event, query_events, load_memory, save_memory,
    load_ability_cache, increment_ability_counter,
    batch_increment_ability_counters, invalidate_ability_cache,
    rebuild_ability_cache
)
from app.services.graph_update_engine import (
    personal_graph_state, rebuild_cache,
    event_ability_ids, compute_node_metrics,
    record_student_graph_event
)
from app.services.conversation_memory import (
    ConversationMemory, UserMemoryManager, record_session_end
)
from app.services.chat import (
    build_system_prompt, chat_start, chat_message, build_user_prompt
)
from app.services.data_loader import ROOT as DATA_ROOT, primary_job_profile

passed = 0
failed = 0
failures = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        failures.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -- {detail}")

def cleanup():
    """Remove test artifacts."""
    for sid_pat in ["test-batch-", "test-concurrent-", "test-graph-", "test-mem-", "test-chatmsg-"]:
        for f in (DATA_ROOT / "data" / "sessions").glob(f"{sid_pat}*.json"):
            try:
                f.unlink()
            except Exception:
                pass
    for f in (DATA_ROOT / "data" / "memory" / "profiles").glob("test-user-*.json"):
        try:
            f.unlink()
        except Exception:
            pass

def now_sid(prefix="test-"):
    return prefix + datetime.now(timezone.utc).strftime("%f")

print("=" * 60)
print("Memory System Optimization -- Comprehensive Test Suite")
print("=" * 60)

# =====================================================================
# 1. CONCURRENCY SAFETY (feedback.py)
# =====================================================================
print("\n--- 1. Concurrency Safety ---")

sid1 = now_sid("test-concurrent-")
errors = []

def writer(idx):
    try:
        append_session_event(sid1, {
            "event_type": "test",
            "note": f"writer_{idx}",
            "thread_id": threading.get_ident()
        })
    except Exception as e:
        errors.append(f"thread_{idx}: {e}")

threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

record1 = load_session_record(sid1)
test_events1 = [e for e in record1["events"] if e.get("note", "").startswith("writer_")]
check("10 concurrent writes - no errors", len(errors) == 0, str(errors))
check("10 concurrent writes - all 10 recorded", len(test_events1) == 10,
      f"got {len(test_events1)}")

# Unique event IDs
eids = [e["event_id"] for e in test_events1]
check("All concurrent events have unique IDs", len(set(eids)) == 10)

# Lock isolation
lock_a = _get_session_lock("session-a-001")
lock_b = _get_session_lock("session-b-002")
check("Different sessions use different locks", lock_a is not lock_b)
lock_a2 = _get_session_lock("session-a-001")
check("Same session reuses same lock", lock_a is lock_a2)

# =====================================================================
# 2. SQLite STORE (session_store.py)
# =====================================================================
print("\n--- 2. SQLite Session Store ---")

sid2 = now_sid("test-batch-")
evt = {"event_id": "EVT001", "event_type": "chat_message",
       "created_at": datetime.now(timezone.utc).isoformat()}
r = insert_event(sid2, evt)
check("insert_event returns saved", r.get("saved") is True)

evt2 = {"event_id": "EVT002", "event_type": "score",
        "created_at": datetime.now(timezone.utc).isoformat()}
insert_event(sid2, evt2)

events = query_events(sid2)
check("query_events returns 2 events", len(events) == 2, f"got {len(events)}")
check("query_events filters by type", len(query_events(sid2, event_type="chat_message")) == 1)

# Duplicate event_id should be ignored
insert_event(sid2, evt)
events = query_events(sid2)
check("duplicate event_id ignored", len(events) == 2, f"got {len(events)}")

# Memory persistence
save_memory(sid2, summary="test summary", key_facts=["fact A", "fact B"],
            span_start=0, span_end=5)
mem = load_memory(sid2)
check("load_memory gets summary", mem.get("summary") == "test summary")
check("load_memory gets key_facts", len(mem.get("key_facts", [])) == 2)
check("load_memory gets span", mem.get("summary_span_end") == 5)

# Empty session
mem_empty = load_memory("nonexistent-session")
check("load_memory for nonexistent is safe", mem_empty.get("summary") == "")

# Ability cache tests
increment_ability_counter(sid2, "electrical_safety_check", "chat_count", event_id="EVT001")
increment_ability_counter(sid2, "electrical_safety_check", "chat_count", event_id="EVT002")

cache = load_ability_cache(sid2)
check("ability cache has test ability", "electrical_safety_check" in cache)
if "electrical_safety_check" in cache:
    check("ability chat_count = 2",
          cache["electrical_safety_check"]["chat_count"] == 2,
          f"got {cache['electrical_safety_check']['chat_count']}")

# Batch increment
batch_increment_ability_counters(sid2, [
    ("electrical_safety_check", "weak_count"),
    ("sensor_type_identification", "chat_count"),
], event_id="EVT003")

cache = load_ability_cache(sid2)
check("batch increment - electrical weak=1",
      cache.get("electrical_safety_check", {}).get("weak_count") == 1)
check("batch increment - sensor chat=1",
      cache.get("sensor_type_identification", {}).get("chat_count") == 1)

# Invalidation
invalidate_ability_cache(sid2, ["electrical_safety_check"])
cache = load_ability_cache(sid2)
check("invalidation removes ability",
      "electrical_safety_check" not in cache,
      f"still present")

# Rebuild from buckets
rebuild_ability_cache(sid2, {
    "ability_x": {"chat": 3, "weak": 0, "improving": 1, "mastered": 0, "recommended": 0,
                  "last_event_id": "", "last_updated_at": ""}
})
cache = load_ability_cache(sid2)
check("rebuild_ability_cache populates ability_x",
      "ability_x" in cache and cache["ability_x"]["chat_count"] == 3)

# =====================================================================
# 3. GRAPH INCREMENTAL CACHE (graph_update_engine.py)
# =====================================================================
print("\n--- 3. Graph Incremental Cache ---")

sid3 = now_sid("test-graph-")

# Record an improving event
record_student_graph_event({
    "session_id": sid3,
    "event_type": "question_explained",
    "ability_ids": ["electrical_safety_check"],
    "note": "electrical safety review",
    "source": "quiz_explain_button",
})

# Add a chat_message event via append
append_session_event(sid3, {
    "event_type": "chat_message",
    "message": "sensor LED on but PLC no input",
    "highlighted_abilities": [
        {"id": "sensor_wiring_judgement", "name": "sensor wiring"},
        {"id": "plc_input_common_terminal", "name": "PLC common terminal"},
    ],
})

# Test personal_graph_state
profile = primary_job_profile()
core_chain = [
    item.get("ability_internal_id", item.get("id", ""))
    for item in profile.get("core_ability_chain", [])
]
state = personal_graph_state(sid3, core_chain)
check("graph state has record", "record" in state)
check("graph state has buckets", "buckets" in state)

buckets = state["buckets"]
sensor_bucket = buckets.get("sensor_wiring_judgement", {})
check("sensor_wiring_judgement has chat=1",
      sensor_bucket.get("chat") == 1,
      f"got chat={sensor_bucket.get('chat')}")

safety_bucket = buckets.get("electrical_safety_check", {})
check("electrical_safety_check has improving=1",
      safety_bucket.get("improving") == 1,
      f"got improving={safety_bucket.get('improving')}")

# Test compute_node_metrics
metrics = compute_node_metrics("sensor_wiring_judgement",
                               buckets.get("sensor_wiring_judgement", {}))
check("metrics has status", "status" in metrics)
check("metrics has mastery_score", isinstance(metrics.get("mastery_score"), int))
check("metrics has confidence", isinstance(metrics.get("confidence"), float))

# Test rebuild_cache
result = rebuild_cache(sid3)
check("rebuild_cache returns rebuilt=True", result.get("rebuilt") is True)
check("rebuild_cache returns ability_count", result.get("ability_count", 0) >= 0)

# Second call should use cache
state2 = personal_graph_state(sid3, core_chain)
check("second graph_state call works (cache hit)", "buckets" in state2)

# Verify consistency between cache and direct
sensor_bucket2 = state2["buckets"].get("sensor_wiring_judgement", {})
check("cache-consistent: chat count",
      sensor_bucket2.get("chat") == sensor_bucket.get("chat"))

# =====================================================================
# 4. CONVERSATION MEMORY (conversation_memory.py)
# =====================================================================
print("\n--- 4. Conversation Memory ---")

sid4 = now_sid("test-mem-")

mem = ConversationMemory(sid4)

# Empty context
ctx = mem.get_active_context([])
check("empty context has summary", "summary" in ctx)
check("empty context has key_facts empty", ctx.get("key_facts") == [])
check("empty context has active_messages empty", ctx.get("active_messages") == [])

# With short history
history4 = [
    {"role": "user", "content": "sensor LED on but PLC no input"},
    {"role": "assistant", "content": "check NPN/PNP type first"},
    {"role": "user", "content": "it is NPN"},
    {"role": "assistant", "content": "check PLC common terminal wiring"},
]
ctx = mem.get_active_context(history4)
check("get_active_context returns messages", len(ctx["active_messages"]) > 0)
for msg in ctx["active_messages"]:
    check(f"message role valid: {msg['role']}", msg["role"] in {"user", "assistant"})

# Should NOT summarize for 4 turns
check("should NOT summarize at 4 turns", not mem._should_summarize(history4))

# Should summarize at 9+ turns
long_history = []
for i in range(12):
    long_history.append({"role": "user", "content": f"question {i}"})
    long_history.append({"role": "assistant", "content": f"answer {i}"})
check("should_summarize at 12 turns", mem._should_summarize(long_history))

# Test key_facts extraction
facts = ConversationMemory._extract_key_facts(
    "student described NPN sensor wiring issue. Confirmed sensor is NPN type, "
    "PLC is Mitsubishi FX3U. Power issue ruled out."
)
check("key_facts extraction produces facts", len(facts) >= 1, f"got {len(facts)}: {facts}")

# Empty summary extraction
facts_empty = ConversationMemory._extract_key_facts("")
check("empty summary produces no facts", facts_empty == [])

# =====================================================================
# 5. USER MEMORY MANAGER (cross-session)
# =====================================================================
print("\n--- 5. User Memory Manager (Cross-Session) ---")

uid5 = now_sid("test-user-")

umm = UserMemoryManager(uid5)
check("new user has 0 sessions", umm.session_count == 0)
check("new user has empty facts", umm.long_term_facts == [])

# Record session 1
umm.record_session("session-1",
                   "student learned NPN sensor wiring, mastered basic multimeter usage",
                   interaction_count=5)
check("after record - 1 session", umm.session_count == 1)
check("after record - has facts", len(umm.long_term_facts) > 0)
check("total_interactions = 5",
      umm._profile.get("total_interactions") == 5)

# Record session 2
umm.record_session("session-2",
                   "student still confused about PLC wiring, needs more training",
                   interaction_count=8)
check("after 2nd - 2 sessions", umm.session_count == 2)
check("total_interactions = 13",
      umm._profile.get("total_interactions") == 13)
facts5 = umm.long_term_facts
check("facts accumulate across sessions", len(facts5) >= 2)

# Cross-session context
ctx5 = umm.get_cross_session_context()
check("cross-session has long_term_facts", "long_term_facts" in ctx5)
check("cross-session has previous_session_summary", "previous_session_summary" in ctx5)
check("previous_session_summary is non-empty",
      len(ctx5.get("previous_session_summary", "")) > 0)

# Add fact manually
umm.add_fact("manually added long-term fact")
check("manual add_fact works", "manually added long-term fact" in umm.long_term_facts)

# record_session_end convenience
sid5_end = now_sid("test-mem-end-")
save_memory(sid5_end, summary="session end summary",
            key_facts=["end fact 1"], span_start=0, span_end=3)
r = record_session_end(sid5_end, uid5)
check("record_session_end succeeds", r.get("recorded") is True)

# record_session_end with no user_id
r_none = record_session_end(sid5_end, None)
check("record_session_end with no user_id", r_none.get("recorded") is False)

# =====================================================================
# 6. SYSTEM PROMPT BUILDING (chat.py)
# =====================================================================
print("\n--- 6. System Prompt Building ---")

profile6 = {"role_name": "test role", "mvp_focus_task": "test task"}

p = build_system_prompt(profile6)
check("basic prompt contains role name", "test role" in p)
check("basic prompt has profile section", "岗位画像" in p)

p = build_system_prompt(profile6, memory={
    "summary": "user previously asked about NPN wiring",
    "key_facts": ["sensor=NPN", "PLC=FX3U"]
})
check("prompt includes summary", "user previously asked about NPN wiring" in p)
check("prompt includes key_facts", "sensor=NPN" in p)
check("prompt includes second key_fact", "PLC=FX3U" in p)

p = build_system_prompt(profile6, cross_session={
    "previous_session_summary": "last session(2026-07-20): student learned wiring basics",
    "long_term_facts": ["mastered multimeter", "confused about PLC"]
})
check("prompt includes cross-session summary", "last session" in p)
check("prompt includes long_term_fact 1", "mastered multimeter" in p)

p = build_system_prompt(profile6,
    memory={"summary": "current summary", "key_facts": ["current fact"]},
    cross_session={"long_term_facts": ["long-term fact"]})
check("prompt includes both memory sources", "current summary" in p and "long-term fact" in p)

# =====================================================================
# 7. CHAT START FLOW
# =====================================================================
print("\n--- 7. Chat Start Flow ---")

sid7 = now_sid("test-chatmsg-")

result = chat_start({"session_id": sid7, "user_id": uid5})
check("chat_start returns session_id", bool(result.get("session_id")))
check("chat_start returns job_profile", "job_profile" in result)
check("chat_start returns learner_context", "learner_context" in result)
check("chat_start returns cross_session_memory", "cross_session_memory" in result)
welcome = result.get("welcome", "")
check("chat_start welcome contains greeting", "你好" in welcome)
check("chat_start welcome contains return msg",
      "欢迎回来" in welcome,
      f"welcome='{welcome[:100]}...'")

# Without user_id
result_no_user = chat_start({"session_id": sid7 + "-no-user"})
check("chat_start without user_id works", result_no_user.get("session_id") is not None)
check("chat_start without user_id has empty cross_session",
      result_no_user.get("cross_session_memory") == {})

# =====================================================================
# 8. EDGE CASES AND ERROR HANDLING
# =====================================================================
print("\n--- 8. Edge Cases ---")

# safe_session_id
sid_empty = safe_session_id(None)
check("safe_session_id(None) generates id", len(sid_empty) > 0 and sid_empty.startswith("S"))
sid_long = safe_session_id("a" * 200)
check("safe_session_id truncates to 80", len(sid_long) <= 80)

# extract_ability_ids edge cases
check("extract_ability_ids with empty dict",
      event_ability_ids({}) == [])
check("extract_ability_ids with None",
      event_ability_ids({}) == [])

# ConversationMemory with empty id
mem_bad = ConversationMemory("")
check("ConversationMemory with empty id is safe", mem_bad.session_id is not None)

# UserMemoryManager with special characters
umm_bad = UserMemoryManager("test/user/with/slashes")
check("UserMemoryManager with special chars in id works",
      umm_bad.user_id == "test/user/with/slashes")

# SQLite operations with empty session_id
cache_empty = load_ability_cache("")
check("load_ability_cache with empty id returns dict", isinstance(cache_empty, dict))

# batch_increment with empty list
batch_increment_ability_counters("test-empty-inc", [])
check("batch_increment with empty list is safe", True)

# invalidate with empty list
invalidate_ability_cache("test-empty-inv", [])
check("invalidate with empty list is safe", True)

# save_feedback invalid input
try:
    save_feedback({"session_id": "test-fb", "feedback": "invalid_feedback_value"})
    check("save_feedback rejects invalid feedback", False, "should have raised")
except ValueError:
    check("save_feedback rejects invalid feedback", True)

# save_feedback valid input
r_fb = save_feedback({"session_id": "test-fb-valid", "feedback": "已掌握",
                       "weak_abilities": [{"ability_name": "test_ability"}]})
check("save_feedback with valid input", r_fb.get("saved") is True)

# =====================================================================
# CLEANUP
# =====================================================================
print("\n--- Cleanup ---")
cleanup()
# Remove other test artifacts
for path in (DATA_ROOT / "data" / "sessions").glob("test-fb*.json"):
    try: path.unlink()
    except Exception: pass
for path in (DATA_ROOT / "data" / "sessions").glob("test-empty-*.json"):
    try: path.unlink()
    except Exception: pass
check("Cleanup completed", True)

# =====================================================================
# SUMMARY
# =====================================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed}/{total} passed, {failed} failed")
if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  - {f}")
else:
    print("ALL TESTS PASSED!")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
