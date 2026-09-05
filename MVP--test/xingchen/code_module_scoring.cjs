const fs = require("fs");
const path = require("path");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function loadDefaultData() {
  const root = path.resolve(__dirname, "..");
  return {
    questions: readJson(path.join(root, "diagnosis", "diagnostic_questions.json")),
    rules: readJson(path.join(root, "diagnosis", "scoring_rules.json"))
  };
}

function shortQuestionId(questionId) {
  const match = String(questionId).match(/^Q0*(\d+)$/i);
  return match ? `Q${String(Number(match[1])).padStart(2, "0")}` : String(questionId);
}

function longQuestionId(questionId) {
  const match = String(questionId).match(/^Q0*(\d+)$/i);
  return match ? `Q${String(Number(match[1])).padStart(3, "0")}` : String(questionId);
}

function normalizeChoice(value) {
  return String(value || "").trim().toUpperCase();
}

function normalizeChoiceList(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeChoice).filter(Boolean);
  }

  const raw = String(value || "").trim().toUpperCase();
  if (!raw) {
    return [];
  }

  if (/[,，\s|>]+/.test(raw)) {
    return raw.split(/[,，\s|>]+/).map(normalizeChoice).filter(Boolean);
  }

  if (/^[A-Z]+$/.test(raw) && raw.length > 1) {
    return raw.split("");
  }

  return [raw];
}

function sameSet(left, right) {
  const a = normalizeChoiceList(left).sort();
  const b = normalizeChoiceList(right).sort();
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function sameOrder(left, right) {
  const a = normalizeChoiceList(left);
  const b = normalizeChoiceList(right);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function isCorrect(answer, question) {
  if (answer === undefined || answer === null || answer === "") {
    return false;
  }

  if (question.type === "multiple_choice") {
    return sameSet(answer, question.correct_answer);
  }

  if (question.type === "ordering") {
    return sameOrder(answer, question.correct_answer);
  }

  return normalizeChoice(answer) === normalizeChoice(question.correct_answer);
}

function buildQuestionMaps(questionData) {
  const byLongId = new Map();
  const byShortId = new Map();

  for (const question of questionData.questions || []) {
    byLongId.set(question.id, question);
    byShortId.set(shortQuestionId(question.id), question);
  }

  return { byLongId, byShortId };
}

function questionRuleFor(rules, questionId) {
  const questionRules = rules.questions || {};
  return questionRules[questionId] || questionRules[longQuestionId(questionId)] || questionRules[shortQuestionId(questionId)] || {};
}

function addUnique(list, seen, value) {
  if (value && !seen.has(value)) {
    seen.add(value);
    list.push(value);
  }
}

function addWeakAbility(output, seen, abilityKey, reason, rules) {
  const catalog = (rules.ability_catalog || {})[abilityKey] || {};
  const abilityId = catalog.ability_id || abilityKey;

  if (seen.has(abilityId)) {
    return;
  }

  seen.add(abilityId);
  output.push({
    ability_id: abilityId,
    ability_name: catalog.ability_name || abilityKey,
    reason: reason || catalog.default_reason || "该能力点对应诊断题回答错误"
  });
}

function feedbackLevel(score, weakAbilities, rules) {
  const critical = new Set(rules.critical_abilities || []);
  const hasCriticalWeakness = weakAbilities.some((item) => critical.has(item.ability_id));

  if (score < 100 && hasCriticalWeakness) {
    return "需要补基础";
  }

  const levels = (rules.feedback_levels || []).slice().sort((a, b) => b.min_score - a.min_score);
  const matched = levels.find((level) => score >= level.min_score);
  return matched ? matched.label : "需要补基础";
}

function scoreDiagnostic(input, data) {
  const loaded = data || loadDefaultData();
  const questionData = loaded.questions;
  const rules = loaded.rules;
  const answers = (input && input.answers) || {};
  const { byShortId } = buildQuestionMaps(questionData);
  const weakAbilities = [];
  const weakSeen = new Set();
  const recommendedPath = [];
  const pathSeen = new Set();
  let correctCount = 0;

  for (const [questionId, question] of byShortId.entries()) {
    const answer = answers[questionId] !== undefined ? answers[questionId] : answers[question.id];
    const correct = isCorrect(answer, question);

    if (correct) {
      correctCount += 1;
      continue;
    }

    const rule = questionRuleFor(rules, question.id);
    const reason = rule.reason || question.wrong_feedback;

    for (const abilityKey of rule.weak_abilities || [question.ability_id]) {
      addWeakAbility(weakAbilities, weakSeen, abilityKey, reason, rules);
    }

    for (const item of rule.recommended_path || []) {
      addUnique(recommendedPath, pathSeen, item);
    }
  }

  const totalCount = byShortId.size;
  const score = totalCount ? Math.round((correctCount / totalCount) * 100) : 0;

  return {
    score,
    correct_count: correctCount,
    total_count: totalCount,
    weak_abilities: weakAbilities,
    recommended_path: recommendedPath,
    feedback_level: feedbackLevel(score, weakAbilities, rules)
  };
}

function main(input) {
  return scoreDiagnostic(input);
}

if (require.main === module) {
  const raw = fs.readFileSync(0, "utf8").trim();
  const input = raw ? JSON.parse(raw) : { answers: {} };
  process.stdout.write(JSON.stringify(main(input), null, 2));
}

module.exports = {
  main,
  scoreDiagnostic
};
