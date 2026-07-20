# -*- coding: utf-8 -*-
"""Conversation memory — sliding window + progressive summarization.

Instead of hard-truncating chat history at 8 turns, this module maintains:
  1. Active window: last N turns kept verbatim as LLM messages
  2. Compressed summary: older turns summarized via LLM into a short paragraph
  3. Key facts: bullet-point facts extracted from the summary, injected into
     the system prompt

The module works per-session. Summaries are stored in the session JSON and
in the session_store SQLite table for fast lookup.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .feedback import load_session_record, safe_session_id

ROOT = Path(__file__).resolve().parents[2]
SUMMARIZE_PROMPT_PATH = ROOT / "prompts" / "memory_summarize_prompt.md"

# When the active window exceeds this many turns, older turns are summarized
SUMMARY_TRIGGER_TURNS = 8
# After the first summary, a new incremental summary is triggered every
# SUMMARY_INCREMENT_TURNS additional turns
SUMMARY_INCREMENT_TURNS = 4
# Maximum turns kept in the active window
MAX_ACTIVE_TURNS = 8

logger = logging.getLogger(__name__)


def _load_summarize_prompt() -> str:
    if SUMMARIZE_PROMPT_PATH.exists():
        return SUMMARIZE_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "你是一个对话摘要助手。请将以下机电一体化实训对话压缩为一段不超过150字的摘要，"
        "保留：核心问题描述、已确认的关键事实、排查进展和结论、待解决问题。"
        "不要重复日常寒暄。只输出摘要文本，不要带任何前缀或后缀。"
    )


# ── ConversationMemory (per-session) ────────────────────────────────

class ConversationMemory:
    """Manages conversation context for a single session.

    Usage in chat handlers:

        memory = ConversationMemory(session_id)
        context = memory.get_active_context(history_from_frontend)
        # context.messages  → list of {"role": …, "content": …} for LLM call
        # context.summary   → str summary to inject into system prompt
        # context.key_facts → list[str] key facts to inject
    """

    def __init__(self, session_id: str):
        self.session_id = safe_session_id(session_id)
        self._record = load_session_record(self.session_id)
        self._memory = self._load_memory()

    # ── internal ───────────────────────────────────────────────────

    def _load_memory(self) -> dict:
        """Load memory from session JSON or SQLite."""
        mem = self._record.get("memory")
        if mem and isinstance(mem, dict):
            return mem

        # Try SQLite
        try:
            from .session_store import load_memory as sqlite_load_memory

            row = sqlite_load_memory(self.session_id)
            if row.get("summary") or row.get("key_facts"):
                return {
                    "summary": row.get("summary", ""),
                    "key_facts": row.get("key_facts", []),
                    "summary_span_start": row.get("summary_span_start", 0),
                    "summary_span_end": row.get("summary_span_end", 0),
                    "updated_at": row.get("updated_at", ""),
                }
        except Exception:
            pass

        return {
            "summary": "",
            "key_facts": [],
            "summary_span_start": 0,
            "summary_span_end": 0,
            "updated_at": "",
        }

    def _save_memory(self):
        """Persist memory to both session JSON and SQLite."""
        # Update in-memory record
        self._record["memory"] = self._memory
        # Write to JSON
        from .feedback import write_session_record

        write_session_record(self._record)

        # Write to SQLite
        try:
            from .session_store import save_memory as sqlite_save_memory

            sqlite_save_memory(
                self.session_id,
                summary=self._memory.get("summary", ""),
                key_facts=self._memory.get("key_facts", []),
                span_start=self._memory.get("summary_span_start", 0),
                span_end=self._memory.get("summary_span_end", 0),
            )
        except Exception:
            pass

    def _count_turns(self, history: list[dict]) -> int:
        """Count conversation turns (user-assistant pairs)."""
        count = 0
        for item in history or []:
            role = item.get("role", "")
            if role == "user":
                count += 1
        return count

    def _should_summarize(self, history: list[dict]) -> bool:
        """Check whether the history has grown enough to trigger summarization."""
        total_turns = self._count_turns(history)
        # First summary trigger
        if total_turns > SUMMARY_TRIGGER_TURNS and not self._memory.get("summary"):
            return True
        # Incremental summary trigger
        covered = self._memory.get("summary_span_end", 0)
        if total_turns > covered + SUMMARY_INCREMENT_TURNS:
            return True
        return False

    def _get_summarizable_turns(self, history: list[dict]):
        """Return the turns that should be summarized (everything outside the active window)."""
        turns = []
        current_turn = 0
        for item in history or []:
            role = item.get("role", "")
            if role not in {"user", "assistant"}:
                continue
            if not item.get("content"):
                continue
            turns.append(item)
            if role == "user":
                current_turn += 1
            # Stop when we reach the active window start
            if current_turn >= len(turns) - MAX_ACTIVE_TURNS:
                break

        # Return turns up to MAX_ACTIVE_TURNS from the end
        total_user_turns = self._count_turns(history)
        if total_user_turns <= MAX_ACTIVE_TURNS:
            return []
        # Count turns from the end to find the cutoff
        user_turns_seen = 0
        cutoff_idx = len(turns)
        for i in range(len(turns) - 1, -1, -1):
            if turns[i].get("role") == "user":
                user_turns_seen += 1
            if user_turns_seen >= MAX_ACTIVE_TURNS:
                cutoff_idx = i
                break
        return turns[:cutoff_idx]

    # ── public API ──────────────────────────────────────────────────

    def get_active_context(self, history: list[dict] | None = None,
                           max_turns: int = MAX_ACTIVE_TURNS) -> dict:
        """Return the assembled context for LLM consumption.

        Returns:
            {
                "summary": str,          # compressed summary of older turns
                "key_facts": list[str],  # bullet-point facts
                "active_messages": list[dict],  # last N turns as LLM messages
            }
        """
        history = history or []
        active = history[-max_turns * 2:]  # approximate: 2 messages per turn
        # Filter to only user/assistant roles
        active_messages = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in active
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        return {
            "summary": self._memory.get("summary", ""),
            "key_facts": self._memory.get("key_facts", []),
            "active_messages": active_messages[-max_turns * 2:],
        }

    def summarize_async(self, history: list[dict],
                        user_id: str | None = None) -> bool:
        """Attempt to generate/update summary. Returns True if summarization ran.

        Call this after sending the LLM response to the user, so summarization
        does not block the main chat flow.
        """
        if not self._should_summarize(history):
            return False

        turns_to_summarize = self._get_summarizable_turns(history)
        if not turns_to_summarize:
            return False

        # Build text to summarize
        conversation_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')[:200]}"
            for item in turns_to_summarize[-20:]  # at most 20 messages
        )

        try:
            from .llm_client import chat_completion, is_configured

            if not is_configured():
                return False

            prompt = _load_summarize_prompt()
            existing = self._memory.get("summary", "")
            if existing:
                user_msg = (
                    f"现有摘要：\n{existing}\n\n"
                    f"新增对话：\n{conversation_text}\n\n"
                    "请将上述信息合并为一段不超过150字的更新摘要。"
                )
            else:
                user_msg = f"对话记录：\n{conversation_text}\n\n请生成摘要。"

            summary = chat_completion(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                timeout=20,
            )
            if summary and summary.strip():
                self._memory["summary"] = summary.strip()
                self._memory["summary_span_end"] = self._count_turns(history)
                self._memory["updated_at"] = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
                # Extract key facts from summary
                self._memory["key_facts"] = self._extract_key_facts(summary)
                self._save_memory()
                return True

        except Exception as exc:
            logger.warning("Conversation summarization failed: %s", exc)

        return False

    @staticmethod
    def _extract_key_facts(summary: str) -> list[str]:
        """Simple extraction of key facts from a summary string.

        For MVP, this is rule-based; could be upgraded to LLM extraction later.
        """
        facts = []
        # Extract sentences that contain key indicators
        indicators = ["传感器", "PLC", "接线", "排查", "已确认", "已排除",
                      "型号", "NPN", "PNP", "公共端", "输入灯", "监控", "故障"]
        sentences = summary.replace("；", "。").replace("，", "。").split("。")
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if any(ind in s for ind in indicators) and len(s) > 4:
                facts.append(s[:80])
        return facts[:5]


# ── UserMemoryManager (cross-session long-term memory) ──────────────

_PROFILES_DIR = ROOT / "data" / "memory" / "profiles"


class UserMemoryManager:
    """Manages long-term memory across multiple sessions for the same user.

    Stores user-level facts extracted from session summaries, enabling
    continuity across sessions.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._profile = self._load_or_create()

    def _profile_path(self) -> Path:
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in self.user_id if c.isalnum() or c in "_-")
        return _PROFILES_DIR / f"{safe or 'default'}.json"

    def _load_or_create(self) -> dict:
        path = self._profile_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "user_id": self.user_id,
            "session_history": [],
            "long_term_facts": [],
            "total_sessions": 0,
            "total_interactions": 0,
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }

    def _save(self):
        self._profile["updated_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        self._profile_path().write_text(
            json.dumps(self._profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def long_term_facts(self) -> list[str]:
        return self._profile.get("long_term_facts", [])[-8:]

    @property
    def session_count(self) -> int:
        return self._profile.get("total_sessions", 0)

    def get_cross_session_context(self) -> dict:
        """Return context injectable into system prompt for continuity."""
        history = self._profile.get("session_history", [])
        facts = self.long_term_facts
        result: dict[str, str | list[str]] = {}
        if facts:
            result["long_term_facts"] = facts
        if history:
            prev = history[-1]  # last session summary
            if prev.get("summary"):
                result["previous_session_summary"] = (
                    f"上次会话({prev.get('date', '')})：{prev['summary']}"
                )
        return result

    def record_session(self, session_id: str, summary: str = "",
                       fact_count: int = 0, interaction_count: int = 0):
        """Record a completed session in the user profile."""
        now = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        self._profile.setdefault("session_history", []).append({
            "session_id": session_id,
            "date": now.strftime("%Y-%m-%d"),
            "summary": summary[:200] if summary else "",
            "interactions": interaction_count,
        })
        # Keep at most 10 session summaries
        if len(self._profile["session_history"]) > 10:
            self._profile["session_history"] = self._profile["session_history"][-10:]

        self._profile["total_sessions"] = len(self._profile["session_history"])
        self._profile["total_interactions"] = (
            self._profile.get("total_interactions", 0) + interaction_count
        )
        self._merge_facts_from_summary(summary)
        self._save()

    def _merge_facts_from_summary(self, summary: str):
        """Extract and merge new long-term facts from a session summary."""
        if not summary:
            return
        # Extract facts using same rule-based approach
        new_facts = ConversationMemory._extract_key_facts(summary)
        existing = set(self._profile.get("long_term_facts", []))
        for f in new_facts:
            if f not in existing:
                existing.add(f)
        self._profile["long_term_facts"] = list(existing)[-15:]  # keep at most 15

    def add_fact(self, fact: str):
        """Manually add a long-term fact."""
        existing = set(self._profile.get("long_term_facts", []))
        existing.add(fact[:100])
        self._profile["long_term_facts"] = list(existing)[-15:]
        self._save()


def record_session_end(session_id: str, user_id: str | None = None):
    """Call this when a session ends to persist long-term memory.

    Reads the session summary from ConversationMemory and saves it to
    the user's long-term profile.
    """
    if not user_id:
        return {"recorded": False, "reason": "no user_id provided"}

    mem = ConversationMemory(session_id)
    summary = mem._memory.get("summary", "")
    interaction_count = mem._count_turns(
        mem._record.get("events", [])
    )

    umm = UserMemoryManager(user_id)
    umm.record_session(
        session_id,
        summary=summary,
        interaction_count=interaction_count,
    )
    return {
        "recorded": True,
        "user_id": user_id,
        "session_id": session_id,
        "interaction_count": interaction_count,
    }
