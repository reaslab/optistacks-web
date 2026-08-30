#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

// Allow campaign shadows to be audited without replacing the web baseline.
const ROOT = process.env.REASATLAS_MATH_ROOT
  ? path.resolve(process.env.REASATLAS_MATH_ROOT)
  : path.resolve(import.meta.dirname, "../site/data/shards");
const FORMULA_KEYS = new Set([
  "statement_latex",
  "proof_latex",
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

const FORMULA_CONTROL_CHARACTERS = /[\u0000-\u0009\u000B\u000C\u000E-\u001F\u007F]/g;
const FORMULA_CONTROL_PATTERN = /[\u0000-\u0009\u000B\u000C\u000E-\u001F\u007F]/;
const TAB_TEX_COMMAND = /^(?:o(?:peratorname|imes?|(?=\b|\s|\{|$))|ext(?:style|bf|rm|it|sf|sc|tt|sl|subscript|superscript|less|greater)?(?=\b|\s|\{|$)|frac(?=\b|\s|\{|[0-9])|ilde(?=\b|\s|\{|$)|au(?=\b|[_^{}\s),.;:!?]|$)|heta(?=\b|[_^{}\s),.;:!?]|$)|op(?=\b|\s|\{|$)|hickspace(?=\b|\s|\{|$)|iny(?=\b|[_^{}\s),.;:!?]|$))/;
const TEX_ENVIRONMENTS = "aligned|alignedat|array|bmatrix|Bmatrix|cases|CD|gathered|gather|matrix|pmatrix|psmallmatrix|smallmatrix|split|Vmatrix|vmatrix";

function normalizeEnvironmentEscapes(value) {
  const opener = new RegExp(`(^|[^\\\\A-Za-z])begin\\s*\\{(${TEX_ENVIRONMENTS})\\}`, "g");
  const closer = new RegExp(`(^|[^\\\\A-Za-z])end\\s*\\{(${TEX_ENVIRONMENTS})\\}`, "g");
  return value
    .replace(opener, (_, prefix, environment) => `${prefix}\\begin{${environment}}`)
    .replace(closer, (_, prefix, environment) => `${prefix}\\end{${environment}}`);
}

function normalizeDelimiterEscapes(value) {
  let result = "";
  let displayDepth = 0;
  let environmentDepth = 0;
  const isOptionalRowBreak = (delimiterIndex, delimiter) => delimiter === "["
    && /^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:pt|pc|in|bp|cm|mm|dd|cc|sp|ex|em|mu)\s*\]/i.test(value.slice(delimiterIndex + 1));
  const countDoubledDelimiters = delimiter => {
    let count = 0;
    for (let index = 0; index < value.length;) {
      if (value[index] !== "\\") { index += 1; continue; }
      let end = index;
      while (end < value.length && value[end] === "\\") end += 1;
      if (end - index === 2 && value[end] === delimiter && !isOptionalRowBreak(end, delimiter)) count += 1;
      index = end + (value[end] ? 1 : 0);
    }
    return count;
  };
  const doubledDisplayOpens = countDoubledDelimiters("[");
  const doubledDisplayCloses = countDoubledDelimiters("]");
  const collapseDoubledDisplay = doubledDisplayOpens > 0 && doubledDisplayOpens === doubledDisplayCloses;
  for (let index = 0; index < value.length;) {
    if (value[index] !== "\\") {
      result += value[index++];
      continue;
    }
    let end = index;
    while (end < value.length && value[end] === "\\") end += 1;
    const runLength = end - index;
    const delimiter = value[end] || "";
    if (runLength === 1 && value.startsWith("\\begin{", index)) environmentDepth += 1;
    if (runLength === 1 && value.startsWith("\\end{", index)) environmentDepth = Math.max(0, environmentDepth - 1);
    const isDelimiter = "()[]".includes(delimiter);
    const collapse = isDelimiter && runLength === 2 && (
      (delimiter === "[" || delimiter === "]")
        ? collapseDoubledDisplay && !isOptionalRowBreak(end, delimiter)
        : !displayDepth && !environmentDepth
    );
    result += "\\".repeat(collapse ? 1 : runLength);
    if (collapse || runLength === 1) {
      if (delimiter === "[") displayDepth += 1;
      if (delimiter === "]") displayDepth = Math.max(0, displayDepth - 1);
    }
    index = end;
  }
  return result;
}

function removeOrphanDelimiterClosings(value) {
  let result = "";
  let inlineDepth = 0;
  let displayDepth = 0;
  for (let index = 0; index < value.length;) {
    if (value[index] !== "\\") { result += value[index++]; continue; }
    let end = index;
    while (end < value.length && value[end] === "\\") end += 1;
    const runLength = end - index;
    const delimiter = value[end] || "";
    const pair = runLength % 2 === 1 ? `\\${delimiter}` : "";
    if (pair === "\\(") { inlineDepth += 1; result += "\\".repeat(runLength) + delimiter; index = end + 1; }
    else if (pair === "\\)") { if (inlineDepth > 0) { inlineDepth -= 1; result += "\\".repeat(runLength) + delimiter; } else result += "\\".repeat(runLength - 1); index = end + 1; }
    else if (pair === "\\[") { displayDepth += 1; result += "\\".repeat(runLength) + delimiter; index = end + 1; }
    else if (pair === "\\]") { if (displayDepth > 0) { displayDepth -= 1; result += "\\".repeat(runLength) + delimiter; } else result += "\\".repeat(runLength - 1); index = end + 1; }
    else { result += "\\".repeat(runLength); index = end; }
  }
  return result;
}

function closeUnterminatedDelimiters(value) {
  if (!value.trimEnd().endsWith("\\")) return value;
  const stack = [];
  for (let index = 0; index < value.length;) {
    if (value[index] !== "\\") { index += 1; continue; }
    let end = index;
    while (end < value.length && value[end] === "\\") end += 1;
    const runLength = end - index;
    const delimiter = value[end] || "";
    if (runLength % 2 === 1 && "()[]".includes(delimiter)) {
      const pair = `\\${delimiter}`;
      if (pair === "\\(") stack.push("\\)");
      else if (pair === "\\[") stack.push("\\]");
      else if (stack[stack.length - 1] === pair) stack.pop();
      index = end + 1;
    } else index = end;
  }
  if (!stack.length) return value;
  const trimmed = value.trimEnd();
  const base = trimmed.slice(0, -1);
  return `${base}${stack.reverse().join("")}`;
}

function normalizeFormulaSource(value) {
  let result = String(value || "").normalize("NFC").replace(/\r\n?/g, "\n");
  result = result.replace(FORMULA_CONTROL_CHARACTERS, (control, offset, source) => {
    const next = source.slice(offset + 1);
    if (control === "\t" && TAB_TEX_COMMAND.test(next)) return "\\t";
    if (control !== "\t" && control !== "\n" && /^[A-Za-z]/.test(next)) return "\\";
    return " ";
  });
  result = normalizeEnvironmentEscapes(result).replace(/[\u00A0\u2000-\u200B\u202F\u205F\u3000]/g, " ")
    .replace(/\t/g, " ").replace(/[ \t]*\n[ \t]*/g, " ").replace(/[ ]{2,}/g, " ").trim();
  let repaired = "";
  let inlineDepth = 0;
  let displayDepth = 0;
  for (let index = 0; index < result.length; index += 1) {
    if (result[index] === "\\" && inlineDepth > 0) {
      const missingClose = result.slice(index).match(/^(?:\\[,;:!> ]\s+|\\(?:quad|qquad)\s+|\\\s+)/);
      if (missingClose && /^[A-Za-z]/.test(result[index + missingClose[0].length])) {
        repaired += "\\) ";
        inlineDepth -= 1;
        index += missingClose[0].length - 1;
        continue;
      }
      const punctuatedClose = result.slice(index).match(/^\\([.,;:!?])(?=\s|$)/);
      if (punctuatedClose) {
        repaired += `\\)${punctuatedClose[1]}`;
        inlineDepth -= 1;
        index += punctuatedClose[0].length - 1;
        continue;
      }
    }
    const pair = result.slice(index, index + 2);
    if (pair === "\\(") { inlineDepth += 1; repaired += pair; index += 1; continue; }
    if (pair === "\\)") { inlineDepth = Math.max(0, inlineDepth - 1); repaired += pair; index += 1; continue; }
    if (pair === "\\[") { displayDepth += 1; repaired += pair; index += 1; continue; }
    if (pair === "\\]") {
      if (displayDepth > 0) { displayDepth -= 1; repaired += pair; }
      else if (inlineDepth > 0) { inlineDepth -= 1; repaired += "\\)"; }
      else repaired += pair;
      index += 1;
      continue;
    }
    const previous = result[index - 1] || "";
    const explicitInlineClose = /^\s*\\\)/.test(result.slice(index + 1));
    const explicitDisplayClose = /^\s*\\\]/.test(result.slice(index + 1));
    const next = result[index + 1] || "";
    const closesDoubledParenthesis = previous === ")" && (/\s/.test(next) || !next);
    if (result[index] === ")" && inlineDepth > 0 && !explicitInlineClose && (/\s/.test(previous) || closesDoubledParenthesis)) { repaired += "\\)"; inlineDepth -= 1; }
    else if (result[index] === "]" && displayDepth > 0 && !explicitDisplayClose && /\s/.test(previous)) { repaired += "\\]"; displayDepth -= 1; }
    else repaired += result[index];
  }
  return closeUnterminatedDelimiters(removeOrphanDelimiterClosings(normalizeDelimiterEscapes(repaired)));
}

function normalizeDollarDelimiters(value) {
  return value
    .replace(/\\mathbin\{\\vrule height 1\.4ex depth -0\.3ex width 0\.07ex\\vrule height 0\.07ex depth -0\.02ex width 0\.8ex\}/g, "\\mathbin{\\restriction}")
    .replace(/(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$/g, (_, formula) => `\\[${formula}\\]`)
    .replace(/(?<!\\)\$([^$\n]+?)(?<!\\)\$/g, (_, formula) => `\\(${formula}\\)`)
    .replace(/(?<!\\)\$/g, "\\$");
}

function normalizedFormula(value) {
  return normalizeDollarDelimiters(normalizeFormulaSource(value));
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
  const environmentStack = [];
  for (const match of value.matchAll(/\\(begin|end)\s*\{([^}]+)\}/g)) {
    if (match[1] === "begin") environmentStack.push(match[2]);
    else if (environmentStack.pop() !== match[2]) {
      reasons.push("unbalanced_environments");
      break;
    }
  }
  if (environmentStack.length && !reasons.includes("unbalanced_environments")) reasons.push("unbalanced_environments");
  if (delimiters.inline_open !== delimiters.inline_close) reasons.push("unbalanced_inline_delimiters");
  if (delimiters.display_open !== delimiters.display_close) reasons.push("unbalanced_display_delimiters");
  if (delimiters.inline_dollars % 2 !== 0) reasons.push("unbalanced_inline_dollars");
  if (delimiters.display_dollars % 2 !== 0) reasons.push("unbalanced_display_dollars");
  if (FORMULA_CONTROL_PATTERN.test(value)) reasons.push("control_character_in_formula");
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
  const normalized = inspectFormula(normalizedFormula(value));
  if (result.delimiters.inline_dollars || result.delimiters.display_dollars) dollarDelimitedCount += 1;
  if (!result.reasons.length && !normalized.reasons.length) return;
  issues.push({
    file: path.relative(path.resolve(import.meta.dirname, ".."), file),
    field: key,
    ...context,
    reasons: result.reasons,
    normalized_reasons: normalized.reasons,
    render_repaired: result.reasons.length > 0 && normalized.reasons.length === 0,
    delimiters: result.delimiters,
    normalized_delimiters: normalized.delimiters,
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
    render_repaired_fields: issues.filter(issue => issue.render_repaired).length,
    normalized_invalid_formula_fields: issues.filter(issue => issue.normalized_reasons.length).length,
    status: issues.some(issue => issue.normalized_reasons.length) ? "FAIL" : "PASS",
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
process.exitCode = report.summary.status === "FAIL" ? 1 : 0;
