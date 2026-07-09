# Diagnosis Rule Writer Skill

Use this skill when editing diagnostic questions, scoring rules, answer examples, or common error tags.

## Rule Shape

Each question rule should include:

- `type`
- `node_id`
- `max_score`
- `answer_key` for single choice questions
- `keywords` for short answer questions
- `common_mistakes` when useful

## Quality Checks

- Every `node_id` should exist in `knowledge/ability_nodes.json`.
- Every error `code` should exist in `knowledge/common_errors.json`.
- Keyword points should sum to the max score.
- Run `node tests/scoring.test.js` after changing rules.

