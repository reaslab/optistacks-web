#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "../site/data/shards");
const FORMULA_KEYS = new Set([
  "statement_latex",
  "assumptions_latex",
  "conclusion_latex",
  "equivalent_formulations_latex",
  "nonasymptotic_bound_latex",
  "epsilon_complexity_latex",
  "symbol_latex",
]);

function jsonFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return jsonFiles(target);
    return entry.name.endsWith(".json") ? [target] : [];
  });
}

function countBackslashToken(value, suffix) {
  let count = 0;
  for (let index = 0; index < value.length - suffix.length; index += 1) {
    if (value[index] !== "\\") continue;
    let runLength = 1;
    while (index - runLength >= 0 && value[index - runLength] === "\\") runLength += 1;
    if (runLength % 2 === 1 && value.slice(index + 1, index + 1 + suffix.length) === suffix) count += 1;
  }
  return count;
}

function countDollarTokens(value) {
  let inline = 0;
  let display = 0;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] !== "$" || (index > 0 && value[index - 1] === "\\")) continue;
    if (value[index + 1] === "$") {
      display += 1;
      index += 1;
    } else {
      inline += 1;
    }
  }
  return { inline, display };
}

function inspectFormula(value) {
  const dollars = countDollarTokens(value);
  const delimiters = {
    inline_open: countBackslashToken(value, "("),
    inline_close: countBackslashToken(value, ")"),
    display_open: countBackslashToken(value, "["),
    display_close: countBackslashToken(value, "]"),
    inline_dollars: dollars.inline,
    display_dollars: dollars.display,
  };
  const reasons = [];
  if (delimiters.inline_open !== delimiters.inline_close) reasons.push("unbalanced_inline_delimiters");
  if (delimiters.display_open !== delimiters.display_close) reasons.push("unbalanced_display_delimiters");
  if (delimiters.inline_dollars % 2 !== 0) reasons.push("unbalanced_inline_dollars");
  if (delimiters.display_dollars % 2 !== 0) reasons.push("unbalanced_display_dollars");
  if (/\t|\0/.test(value)) reasons.push("control_character_in_formula");
  if (/Need (?:final|regenerate)|END ANALYSIS|channel (?:final|switch)/i.test(value)) reasons.push("generation_artifact_in_formula");
  return { delimiters, reasons };
}

const issues = [];
const countsByKey = {};
let formulaCount = 0;
let dollarDelimitedCount = 0;

function visit(value, key, file, context = {}) {
  if (Array.isArray(value)) {
    value.forEach(item => visit(item, key, file, context));
    return;
  }
  if (value && typeof value === "object") {
    const nextContext = {
      statement_id: value.id || context.statement_id || null,
      topic_id: value.topic_id || context.topic_id || null,
    };
    Object.entries(value).forEach(([childKey, child]) => visit(child, childKey, file, nextContext));
    return;
  }
  if (typeof value !== "string" || !FORMULA_KEYS.has(key) || !value.trim()) return;
  formulaCount += 1;
  countsByKey[key] = (countsByKey[key] || 0) + 1;
  const result = inspectFormula(value);
  if (result.delimiters.inline_dollars || result.delimiters.display_dollars) dollarDelimitedCount += 1;
  if (!result.reasons.length) return;
  issues.push({
    file: path.relative(path.resolve(import.meta.dirname, ".."), file),
    field: key,
    ...context,
    reasons: result.reasons,
    delimiters: result.delimiters,
    preview: value.slice(0, 500),
  });
}

const files = jsonFiles(ROOT);
for (const file of files) {
  visit(JSON.parse(fs.readFileSync(file, "utf8")), "", file);
}

const report = {
  schema_version: "optistacks-math-rendering-audit-v1",
  generated_at: new Date().toISOString(),
  scanned_directory: path.relative(path.resolve(import.meta.dirname, ".."), ROOT),
  summary: {
    files: files.length,
    formula_fields: formulaCount,
    formula_fields_by_key: countsByKey,
    dollar_delimited_fields: dollarDelimitedCount,
    invalid_formula_fields: issues.length,
    status: issues.length ? "FAIL" : "PASS",
  },
  issues,
};

const outputIndex = process.argv.indexOf("--output");
if (outputIndex >= 0) {
  const outputPath = path.resolve(process.argv[outputIndex + 1]);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
}
console.log(JSON.stringify(report.summary, null, 2));
process.exitCode = issues.length ? 1 : 0;
