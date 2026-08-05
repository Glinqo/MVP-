# Non-Regression Requirements

Critical behaviors that MUST NOT regress across any code change.
Each item maps to at least one automated eval case.

## Hard Gates (block merge)

| # | Requirement | Eval Layer | Case IDs |
|---|-------------|------------|----------|
| 1 | Current message must never be duplicated in output | L3 | MULTI-003 |
| 2 | Short answers must bind to pending_slot | L1 | STATE-002 |
| 3 | Known slots must not be re-asked | L3 | MULTI-003 |
| 4 | New task must reset clarify state | L1 | STATE-005 |
| 5 | Knowledge question during active diagnosis preserves task | L2 | POL-004 |
| 6 | Mixed requests must be able to multi-tool | L2 | POL-003 |
| 7 | One turn produces exactly one assistant final | L3 | MULTI-002 |
| 8 | Sources must not be fabricated | L5 | GRD-002 |
| 9 | Safety bypass requests must be blocked | L5 | SAF-002 |
| 10 | Slot accuracy must be 100% on known patterns | L1 | STATE-001..007 |

## Soft Gates (warning, do not block)

| # | Requirement | Eval Layer |
|---|-------------|------------|
| 1 | Policy tool recall >= 90% | L2 |
| 2 | Forbidden tool rate = 0% | L2 |
| 3 | ActiveTask preservation >= 95% | L2 |
| 4 | Repeated question rate < 5% | L3 |
| 5 | First delta latency < 3s | L6 |
| 6 | LLM call count per turn <= 3 | L6 |

## How to use

Before merging any PR that touches chat/slots/policy/response:

```bash
# Quick gate (pre-commit)
python evals/runners/run_regression.py --quick

# Full gate (pre-merge)
python evals/runners/run_regression.py
```

If hard gates fail, the merge is blocked until fixed.
If soft gates regress, document why and get approval.

## Prompt versions

Record prompt version changes in eval reports:
- `planner_v1`: initial action planner prompt
- `composer_v1`: initial response composer prompt
- `slot_extractor_v1`: initial slot extraction rules

## RAG configuration

Record retrieval config changes:
- `top_k`: default 3
- `knowledge_dataset`: current snapshot date

