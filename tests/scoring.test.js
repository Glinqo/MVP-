const assert = require("assert");
const { scoreDiagnostic } = require("../xingchen/code_module_scoring");

const allCorrect = {
  answers: {
    Q01: "A",
    Q02: ["A", "B", "C", "D"],
    Q03: "B",
    Q04: ["A", "B", "C", "D", "E"],
    Q05: ["A", "B", "C", "D", "E", "F"],
    Q06: "A",
    Q07: "B",
    Q08: ["A", "B", "C", "D"],
    Q09: "A",
    Q10: "B",
    Q11: "A",
    Q12: "C",
    Q13: ["A", "B", "C", "D"],
    Q14: "B",
    Q15: ["A", "B", "C", "D", "E", "F"],
    Q16: "B",
    Q17: ["A", "B", "C", "D"],
    Q18: ["A", "B", "C", "D"],
    Q19: ["A", "B", "C", "D"],
    Q20: "C"
  }
};

const allWrong = {
  answers: {
    Q01: "B",
    Q02: "E",
    Q03: "A",
    Q04: "F",
    Q05: ["F", "E", "D", "C", "B", "A"],
    Q06: "C",
    Q07: "A",
    Q08: ["E", "F"],
    Q09: "D",
    Q10: "A",
    Q11: "B",
    Q12: "A",
    Q13: "E",
    Q14: "A",
    Q15: ["F", "E", "D", "C", "B", "A"],
    Q16: "A",
    Q17: "E",
    Q18: "E",
    Q19: "E",
    Q20: "A"
  }
};

const partialWrong = {
  answers: {
    Q01: "B",
    Q02: "ABCD",
    Q03: "C",
    Q04: "ABCDE",
    Q05: "A,B,C,D,E,F",
    Q06: "A",
    Q07: "B",
    Q08: "A B C D",
    Q09: "A",
    Q10: "B",
    Q11: "A",
    Q12: "C",
    Q13: "ABCD",
    Q14: "B",
    Q15: "A,B,C,D,E,F",
    Q16: "B",
    Q17: "ABCD",
    Q18: "ABCD",
    Q19: "ABCD",
    Q20: "C"
  }
};

const missingAnswers = {
  answers: {
    Q01: "A",
    Q02: ["A", "B", "C", "D"],
    Q06: "A"
  }
};

const perfect = scoreDiagnostic(allCorrect);
assert.deepStrictEqual(perfect, {
  score: 100,
  correct_count: 20,
  total_count: 20,
  weak_abilities: [],
  recommended_path: [],
  feedback_level: "掌握较好"
});

const failed = scoreDiagnostic(allWrong);
assert.strictEqual(failed.score, 0);
assert.strictEqual(failed.correct_count, 0);
assert.strictEqual(failed.total_count, 20);
assert.strictEqual(failed.feedback_level, "需要补基础");
assert(failed.weak_abilities.some((item) => item.ability_id === "A01"));
assert(failed.weak_abilities.some((item) => item.ability_id === "A02"));
assert(failed.weak_abilities.some((item) => item.ability_id === "A03"));
assert(failed.weak_abilities.some((item) => item.ability_id === "A07"));
assert(failed.recommended_path.includes("电气安全检查"));
assert(failed.recommended_path.includes("PLC 输入监控训练"));

const partial = scoreDiagnostic(partialWrong);
assert.strictEqual(partial.score, 90);
assert.strictEqual(partial.correct_count, 18);
assert.strictEqual(partial.total_count, 20);
assert.strictEqual(partial.feedback_level, "需要补基础");
assert.deepStrictEqual(
  partial.weak_abilities.map((item) => item.ability_id),
  ["A02", "A03"]
);
assert.deepStrictEqual(partial.weak_abilities[0], {
  ability_id: "A02",
  ability_name: "NPN/PNP 传感器类型识别",
  reason: "NPN/PNP 输出类型与公共端关系判断错误"
});
assert(partial.recommended_path.includes("接线图判断训练"));

const missing = scoreDiagnostic(missingAnswers);
assert.strictEqual(missing.score, 15);
assert.strictEqual(missing.correct_count, 3);
assert.strictEqual(missing.total_count, 20);
assert.strictEqual(missing.feedback_level, "需要补基础");
assert(missing.weak_abilities.length >= 4);
assert(missing.recommended_path.includes("故障记录复盘"));

console.log("scoring.test.js passed");
