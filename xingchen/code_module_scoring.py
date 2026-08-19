import json
import re
import sys
from pathlib import Path


def read_json(file_path):
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def load_default_data():
    root = Path(__file__).resolve().parent.parent
    return {
        "questions": read_json(root / "diagnosis" / "diagnostic_questions.json"),
        "rules": read_json(root / "diagnosis" / "scoring_rules.json"),
    }


def short_question_id(question_id):
    match = re.match(r"^Q0*(\d+)$", str(question_id), re.I)
    return f"Q{int(match.group(1)):02d}" if match else str(question_id)


def long_question_id(question_id):
    match = re.match(r"^Q0*(\d+)$", str(question_id), re.I)
    return f"Q{int(match.group(1)):03d}" if match else str(question_id)


def normalize_choice(value):
    return str(value or "").strip().upper()


def normalize_choice_list(value):
    if isinstance(value, list):
        return [normalize_choice(item) for item in value if normalize_choice(item)]

    raw = normalize_choice(value)
    if not raw:
        return []

    if re.search(r"[,，\s|>]+", raw):
        return [normalize_choice(item) for item in re.split(r"[,，\s|>]+", raw) if normalize_choice(item)]

    if re.match(r"^[A-Z]+$", raw) and len(raw) > 1:
        return list(raw)

    return [raw]


def same_set(left, right):
    return sorted(normalize_choice_list(left)) == sorted(normalize_choice_list(right))


def same_order(left, right):
    return normalize_choice_list(left) == normalize_choice_list(right)


def is_correct(answer, question):
    if answer is None or answer == "":
        return False

    if question.get("type") == "multiple_choice":
        return same_set(answer, question.get("correct_answer", []))

    if question.get("type") == "ordering":
        return same_order(answer, question.get("correct_answer", []))

    return normalize_choice(answer) == normalize_choice(question.get("correct_answer"))


def build_question_maps(question_data):
    by_short_id = {}
    for question in question_data.get("questions", []):
        by_short_id[short_question_id(question["id"])] = question
    return by_short_id


def question_rule_for(rules, question_id):
    question_rules = rules.get("questions", {})
    return (
        question_rules.get(question_id)
        or question_rules.get(long_question_id(question_id))
        or question_rules.get(short_question_id(question_id))
        or {}
    )


def add_unique(items, seen, value):
    if value and value not in seen:
        seen.add(value)
        items.append(value)


def add_weak_ability(output, seen, ability_key, reason, rules):
    catalog = rules.get("ability_catalog", {}).get(ability_key, {})
    ability_id = catalog.get("ability_id", ability_key)

    if ability_id in seen:
        return

    seen.add(ability_id)
    output.append(
        {
            "ability_id": ability_id,
            "ability_name": catalog.get("ability_name", ability_key),
            "reason": reason or catalog.get("default_reason") or "该能力点对应诊断题回答错误",
        }
    )


def feedback_level(score, weak_abilities, rules):
    critical = set(rules.get("critical_abilities", []))
    has_critical_weakness = any(item.get("ability_id") in critical for item in weak_abilities)

    if score < 100 and has_critical_weakness:
        return "需要补基础"

    levels = sorted(rules.get("feedback_levels", []), key=lambda item: item.get("min_score", 0), reverse=True)
    for level in levels:
        if score >= level.get("min_score", 0):
            return level.get("label", "需要补基础")
    return "需要补基础"



def _load_v2_questions():
    """Load questions from diagnostic_questions_v2.json."""
    try:
        root = Path(__file__).resolve().parent.parent
        v2 = read_json(root / "diagnosis" / "diagnostic_questions_v2.json")
        return _build_v2_map(v2)
    except Exception:
        return {}

def _build_v2_map(v2_data):
    result = {}
    for job_set in (v2_data.get("job_question_sets") or {}).values():
        if isinstance(job_set, list):
            for q in job_set:
                result[q.get("id", "")] = q
    return result

def score_diagnostic(input_data, data=None):
    loaded = data or load_default_data()
    question_data = loaded["questions"]
    rules = loaded["rules"]
    answers = (input_data or {}).get("answers", {})
    questions = build_question_maps(question_data)
    # Also load v2 questions for Qian branch compatibility
    _v2_questions = _load_v2_questions()
    questions.update(_v2_questions)
    weak_abilities = []
    weak_seen = set()
    recommended_path = []
    path_seen = set()
    correct_count = 0
    total_count = 0
    ability_correct = {}
    ability_total = {}
    answered_ability_ids = []

    # Iterate over answers (from front-end) instead of questions, to support v2 QIDs
    for qid, answer in answers.items():
        question = questions.get(qid) or questions.get(short_question_id(qid)) or questions.get(long_question_id(qid))
        if not question:
            continue
        total_count += 1
        ability_id = question.get("ability_id")
        if ability_id:
            if ability_id not in answered_ability_ids:
                answered_ability_ids.append(ability_id)
            ability_total[ability_id] = ability_total.get(ability_id, 0) + 1
            if is_correct(answer, question):
                ability_correct[ability_id] = ability_correct.get(ability_id, 0) + 1

        if is_correct(answer, question):
            correct_count += 1
            continue

        rule = question_rule_for(rules, question["id"])
        reason = rule.get("reason") or question.get("wrong_feedback")

        for ability_key in rule.get("weak_abilities", [question.get("ability_id")]):
            add_weak_ability(weak_abilities, weak_seen, ability_key, reason, rules)

        for item in rule.get("recommended_path", []):
            add_unique(recommended_path, path_seen, item)

    score = round((correct_count / total_count) * 100) if total_count else 0

    ability_scores = {}
    for aid, total in ability_total.items():
        ability_scores[aid] = round((ability_correct.get(aid, 0) / total) * 100) if total else 0

    return {
        "score": score,
        "correct_count": correct_count,
        "total_count": total_count,
        "ability_scores": ability_scores,
        "answered_ability_ids": answered_ability_ids,
        "weak_abilities": weak_abilities,
        "recommended_path": recommended_path,
        "feedback_level": feedback_level(score, weak_abilities, rules),
    }


def main(input_data):
    return score_diagnostic(input_data)


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {"answers": {}}
    print(json.dumps(main(payload), ensure_ascii=False, indent=2))
