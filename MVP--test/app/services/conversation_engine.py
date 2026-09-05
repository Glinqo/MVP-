# -*- coding: utf-8 -*-
"""Conversation Engine - RAG citation system from v7 framework."""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from .retrieval import search_knowledge
from .llm_client import chat_completion, is_configured, LLMError


@dataclass
class RAGCitation:
    ref_id: str
    title: str
    url: str = ''
    content: str = ''
    chunk_id: Optional[str] = None


def _build_citation_map(knowledge_refs):
    """Build citation label -> knowledge item mapping."""
    if not knowledge_refs:
        return {}
    mapping = {}
    for idx, item in enumerate(knowledge_refs[:5]):
        label = chr(26469) + chr(28304) + str(idx + 1)
        mapping[label] = item
    return mapping


def _build_rag_prompt(query, citations):
    """Build RAG prompt with embedded knowledge citations."""
    if not citations:
        return query
    blocks = []
    blocks.append(chr(29992) + chr(25143) + chr(38382) + chr(39064) + chr(65306) + query)
    blocks.append("")
    blocks.append(chr(30456) + chr(20851) + chr(30693) + chr(35782) + chr(65306))
    for idx, c in enumerate(citations):
        blocks.append("[" + chr(26469) + chr(28304) + str(idx+1) + "] " + c.ref_id + " - " + c.title)
        if c.content:
            blocks.append("  " + chr(20869) + chr(23481) + ": " + c.content[:300])
        blocks.append("")
    SRC = chr(26469) + chr(28304)
    blocks.append(chr(35831) + chr(22522) + chr(20110) + chr(20197) + chr(19978) + chr(30693) + chr(35782) + chr(22238) + chr(31572) + chr(65292) + chr(24182) + chr(29992) + "[" + SRC + "N]" + chr(26631) + chr(35760) + chr(24341) + chr(29992) + chr(12290))
    return "\n".join(blocks)


def format_citations(raw_text, citations, max_citations=5):
    """Format citations in output text. Appends formatted citation block."""
    if not citations or not raw_text:
        return raw_text
    cits = citations[:max_citations]
    cit_map = {}
    for i, c in enumerate(cits):
        if isinstance(c, dict):
            pass  # RAGCitation already imported at module level
            cit_map[i+1] = RAGCitation(
                ref_id=c.get("id",""),
                title=c.get("title","") or c.get("topic",""),
                url=c.get("source_url","") or c.get("source",""),
                content=c.get("content","")
            )
        else:
            cit_map[i+1] = c
    # Build citation lines
    lines = []
    for idx in sorted(cit_map.keys()):
        c = cit_map[idx]
        title = c.title or c.ref_id
        src = c.url
        if src:
            lines.append("> **" + chr(0x1F4D6) + " [" + chr(26469) + chr(28304) + str(idx) + "] " + title + chr(8212) + " *" + src[:120] + "*")
        else:
            lines.append("> **" + chr(0x1F4D6) + " [" + chr(26469) + chr(28304) + str(idx) + "] " + title + "**")
    if not lines:
        return raw_text
    # Clean old References
    text = re.sub(r'\*References:.*?\*','',raw_text)
    text = text.rstrip()
    if text.endswith("---"):
        text = text[:-3].rstrip()
    ref_header = chr(0x1F4D6) + " " + chr(21442) + chr(32771) + chr(26469) + chr(28304) + chr(65306)
    return text + "\n\n---\n**" + ref_header + "**\n" + "\n".join(lines)

def generate_with_rag(query, job_role=None, llm_fn=None, top_n=5):
    """Generate answer with RAG citations."""
    sr = search_knowledge(query, limit=top_n, job_role=job_role)
    citations = [RAGCitation(
        ref_id=r.get("id",""),
        title=r.get("title","") or r.get("topic",""),
        url=r.get("source_url","") or r.get("source",""),
        content=r.get("content",""))
        for r in sr
    ]
    if not citations:
        if llm_fn:
            return llm_fn(query)
        return query
    if is_configured() and llm_fn:
        prompt = _build_rag_prompt(query, citations)
        try:
            llm_output = llm_fn(prompt)
            if llm_output:
                return format_citations(llm_output, citations)
        except Exception:
            pass
    return format_citations(query, citations)


def _finalize_message(result, knowledge_refs):
    """Add citations to answer if not already present."""
    if not knowledge_refs or not result:
        return result
    ans = result.get("answer","")
    if not ans:
        return result
    try:
        result['answer'] = format_citations(ans, knowledge_refs)
    except Exception:
        pass
    return result