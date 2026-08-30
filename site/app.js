const state = {
  manifest: null,
  subjectId: null,
  domainMeta: null,
  data: null,
  flat: [],
  byId: new Map(),
  parents: new Map(),
  selected: null,
  expanded: new Set(),
  domainCache: new Map(),
  payloadCache: new Map(),
  payloadRequests: new Map(),
  loadingNodes: new Set(),
  domainLoadToken: 0,
  navigationToken: 0,
  qualityIssues: [],
  qualityTarget: null,
  editingIssueId: null,
  submissionHistory: [],
  submissionView: "queue",
  historyFilter: "all",
  layoutBeforeAnnotation: null,
  statementLimits: new Map(),
};

const QUALITY_STORAGE_KEY = "optistacks-quality-review-v1";
const SUBMISSIONS_STORAGE_KEY = "optistacks-submissions-v1";
const SUBMISSION_HISTORY_STORAGE_KEY = "optistacks-submission-history-v1";
const LAYOUT_STORAGE_KEY = "optistacks-layout-v1";
const SUBMISSION_ENDPOINT = "https://formspree.io/f/xaewkbzw";
const SUBMISSION_TIMEOUT_MS = 10000;
const PANE_LABELS = { library: "domains", directory: "outline", detail: "content" };
const STATEMENT_PAGE_SIZE = 24;
const LEGACY_DOMAIN_ROUTES = {
  derivative_free_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C01",
  },
  manifold_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C02",
  },
  distributed_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C03",
  },
};
const QUALITY_TYPES = {
  statement: [
    ["natural_language", "Natural-language wording"],
    ["mathematical_correctness", "Mathematical correctness"],
    ["missing_assumption", "Missing or incorrect assumption"],
    ["latex_rendering", "Formula or rendering problem"],
    ["statement_placement", "Wrong topic placement"],
    ["duplicate_statement", "Duplicate statement"],
    ["evidence_source", "Evidence or source problem"],
    ["other", "Other statement issue"],
  ],
  topic: [
    ["directory_split", "Topic should be split differently"],
    ["directory_merge", "Topics should be merged"],
    ["hierarchy_placement", "Wrong parent or hierarchy"],
    ["topic_naming", "Topic naming problem"],
    ["missing_topic", "Missing topic or branch"],
    ["duplicate_topic", "Duplicate topic"],
    ["other", "Other directory issue"],
  ],
};

const $ = (selector) => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[char]));
const formatNumber = value => new Intl.NumberFormat("en-US").format(value || 0);
const titleCase = value => String(value || "").replaceAll("_", " ");

const FORMULA_CONTROL_CHARACTERS = /[\u0000-\u0009\u000B\u000C\u000E-\u001F\u007F]/g;

// A malformed JSON export can turn TeX's `\t...` escape into a tab. Only
// restore a tab when the following characters form a known `t` command;
// otherwise it is formatting whitespace and should remain a space.
const TAB_TEX_COMMAND = /^(?:o(?:peratorname|imes?|(?=\b|\s|\{|$))|ext(?:style|bf|rm|it|sf|tt|sl|sc|subscript|superscript|less|greater)?(?=\b|\s|\{|$)|frac(?=\b|\s|\{|[0-9])|ilde(?=\b|\s|\{|$)|au(?=\b|[_^{}\s),.;:!?]|$)|heta(?=\b|[_^{}\s),.;:!?]|$)|op(?=\b|\s|\{|$)|hickspace(?=\b|\s|\{|$)|iny(?=\b|[_^{}\s),.;:!?]|$))/;
const TEX_ENVIRONMENTS = "aligned|alignedat|array|bmatrix|Bmatrix|cases|CD|gathered|gather|matrix|pmatrix|psmallmatrix|smallmatrix|split|Vmatrix|vmatrix";

function restoreFormulaControls(value) {
  return value.replace(FORMULA_CONTROL_CHARACTERS, (control, offset, source) => {
    const next = source.slice(offset + 1);
    if (control === "\t" && TAB_TEX_COMMAND.test(next)) return "\\t";
    // NUL and the other non-printing controls commonly replaced a missing
    // command backslash. Do not add one when the command already has it.
    if (control !== "\t" && control !== "\n" && /^[A-Za-z]/.test(next)) return "\\";
    return " ";
  });
}

function normalizeEnvironmentEscapes(value) {
  const opener = new RegExp(`(^|[^\\\\A-Za-z])begin\\s*\\{(${TEX_ENVIRONMENTS})\\}`, "g");
  const closer = new RegExp(`(^|[^\\\\A-Za-z])end\\s*\\{(${TEX_ENVIRONMENTS})\\}`, "g");
  return value
    .replace(opener, (_, prefix, environment) => `${prefix}\\begin{${environment}}`)
    .replace(closer, (_, prefix, environment) => `${prefix}\\end{${environment}}`);
}

function isOptionalRowBreak(value, delimiterIndex, delimiter) {
  if (delimiter !== "[") return false;
  return /^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:pt|pc|in|bp|cm|mm|dd|cc|sp|ex|em|mu)\s*\]/i.test(value.slice(delimiterIndex + 1));
}

function countDoubledDelimiters(value, delimiter) {
  let count = 0;
  for (let index = 0; index < value.length;) {
    if (value[index] !== "\\") { index += 1; continue; }
    let end = index;
    while (end < value.length && value[end] === "\\") end += 1;
    if (end - index === 2 && value[end] === delimiter && !isOptionalRowBreak(value, end, delimiter)) count += 1;
    index = end + (value[end] ? 1 : 0);
  }
  return count;
}

function normalizeDelimiterEscapes(value) {
  let result = "";
  let displayDepth = 0;
  let environmentDepth = 0;
  const doubledDisplayOpens = countDoubledDelimiters(value, "[");
  const doubledDisplayCloses = countDoubledDelimiters(value, "]");
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
    const isDelimiter = "()[]".includes(delimiter);
    if (runLength === 1 && value.startsWith("\\begin{", index)) environmentDepth += 1;
    if (runLength === 1 && value.startsWith("\\end{", index)) environmentDepth = Math.max(0, environmentDepth - 1);
    // Two slashes before a delimiter are usually an over-escaped delimiter.
    // A display pair is collapsed only when the field contains matching
    // doubled open/close markers; this preserves TeX row breaks such as
    // `\\[2pt]` inside an aligned environment.
    const collapse = isDelimiter && runLength === 2 && (
      (delimiter === "[" || delimiter === "]")
        ? collapseDoubledDisplay && !isOptionalRowBreak(value, end, delimiter)
        : !displayDepth && !environmentDepth
    );
    const outputLength = collapse ? 1 : runLength;
    result += "\\".repeat(outputLength);
    if (collapse) {
      if (delimiter === "[") displayDepth += 1;
      if (delimiter === "]") displayDepth = Math.max(0, displayDepth - 1);
    } else if (runLength === 1 && delimiter === "[") {
      displayDepth += 1;
    } else if (runLength === 1 && delimiter === "]") {
      displayDepth = Math.max(0, displayDepth - 1);
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
    if (value[index] !== "\\") {
      result += value[index++];
      continue;
    }
    let end = index;
    while (end < value.length && value[end] === "\\") end += 1;
    const runLength = end - index;
    const delimiter = value[end] || "";
    const pair = runLength % 2 === 1 ? `\\${delimiter}` : "";
    if (pair === "\\(") {
      inlineDepth += 1;
      result += "\\".repeat(runLength) + delimiter;
      index = end + 1;
    } else if (pair === "\\)") {
      if (inlineDepth > 0) {
        inlineDepth -= 1;
        result += "\\".repeat(runLength) + delimiter;
      }
      else result += "\\".repeat(runLength - 1);
      index = end + 1;
    } else if (pair === "\\[") {
      displayDepth += 1;
      result += "\\".repeat(runLength) + delimiter;
      index = end + 1;
    } else if (pair === "\\]") {
      if (displayDepth > 0) {
        displayDepth -= 1;
        result += "\\".repeat(runLength) + delimiter;
      }
      else result += "\\".repeat(runLength - 1);
      index = end + 1;
    } else {
      result += "\\".repeat(runLength);
      index = end;
    }
  }
  return result;
}

function closeUnterminatedDelimiters(value) {
  // Only a trailing backslash is an unambiguous lost closing delimiter. If
  // prose follows an unmatched opener, leave it isolated as a source error.
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

  result = normalizeEnvironmentEscapes(restoreFormulaControls(result));
  result = result
    .replace(/[\u00A0\u2000-\u200B\u202F\u205F\u3000]/g, " ")
    .replace(/\t/g, " ")
    .replace(/[ \t]*\n[ \t]*/g, " ")
    .replace(/[ ]{2,}/g, " ")
    .trim();

  // Some legacy fields lost the backslash immediately before a closing
  // delimiter when a line break was decoded. Repair only a closing bracket
  // that follows whitespace while its matching opening delimiter is active.
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
    if (pair === "\\(") {
      inlineDepth += 1;
      repaired += pair;
      index += 1;
      continue;
    }
    if (pair === "\\)") {
      inlineDepth = Math.max(0, inlineDepth - 1);
      repaired += pair;
      index += 1;
      continue;
    }
    if (pair === "\\[") {
      displayDepth += 1;
      repaired += pair;
      index += 1;
      continue;
    }
    if (pair === "\\]") {
      if (displayDepth > 0) {
        displayDepth -= 1;
        repaired += pair;
      } else if (inlineDepth > 0) {
        inlineDepth -= 1;
        repaired += "\\)";
      } else repaired += pair;
      index += 1;
      continue;
    }
    const previous = result[index - 1] || "";
    const hasNearbyExplicitInlineClose = /^\s*\\\)/.test(result.slice(index + 1));
    const hasNearbyExplicitDisplayClose = /^\s*\\\]/.test(result.slice(index + 1));
    const next = result[index + 1] || "";
    const closesDoubledParenthesis = previous === ")" && (/\s/.test(next) || !next);
    if (result[index] === ")" && inlineDepth > 0 && !hasNearbyExplicitInlineClose && (/\s/.test(previous) || closesDoubledParenthesis)) {
      repaired += "\\)";
      inlineDepth -= 1;
    } else if (result[index] === "]" && displayDepth > 0 && !hasNearbyExplicitDisplayClose && /\s/.test(previous)) {
      repaired += "\\]";
      displayDepth -= 1;
    } else {
      repaired += result[index];
    }
  }
  return closeUnterminatedDelimiters(removeOrphanDelimiterClosings(normalizeDelimiterEscapes(repaired)));
}

function normalizeDollarDelimiters(value) {
  return value
    .replace(/\\mathbin\{\\vrule height 1\.4ex depth -0\.3ex width 0\.07ex\\vrule height 0\.07ex depth -0\.02ex width 0\.8ex\}/g, "\\mathbin{\\restriction}")
    .replace(/(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$/g, (_, formula) => `\\[${formula}\\]`)
    .replace(/(?<!\\)\$([^$\n]+?)(?<!\\)\$/g, (_, formula) => `\\(${formula}\\)`)
    // Keep an unmatched currency marker literal instead of letting MathJax
    // treat it as the start of a math span that consumes following prose.
    .replace(/(?<!\\)\$/g, "\\$");
}

function delimiterCounts(value) {
  const count = pattern => (value.match(pattern) || []).length;
  const withoutDisplayDollars = value.replace(/(?<!\\)\$\$/g, "");
  return {
    inlineOpen: count(/(?<!\\)\\\(/g),
    inlineClose: count(/(?<!\\)\\\)/g),
    displayOpen: count(/(?<!\\)\\\[/g),
    displayClose: count(/(?<!\\)\\\]/g),
    displayDollars: count(/(?<!\\)\$\$/g),
    inlineDollars: (withoutDisplayDollars.match(/(?<!\\)\$/g) || []).length,
  };
}

function hasBalancedDelimiters(value) {
  const counts = delimiterCounts(value);
  const environmentStack = [];
  for (const match of value.matchAll(/\\(begin|end)\s*\{([^}]+)\}/g)) {
    if (match[1] === "begin") environmentStack.push(match[2]);
    else if (environmentStack.pop() !== match[2]) return false;
  }
  return !environmentStack.length
    && counts.inlineOpen === counts.inlineClose
    && counts.displayOpen === counts.displayClose
    && counts.displayDollars % 2 === 0
    && counts.inlineDollars % 2 === 0;
}

function trimOrphanTrailingDelimiter(value) {
  let result = value;
  let counts = delimiterCounts(result);
  while (counts.inlineClose === counts.inlineOpen + 1 && /\\\)\s*$/.test(result)) {
    result = result.replace(/\\\)\s*$/, "").trimEnd();
    counts = delimiterCounts(result);
  }
  while (counts.displayClose === counts.displayOpen + 1 && /\\\]\s*$/.test(result)) {
    result = result.replace(/\\\]\s*$/, "").trimEnd();
    counts = delimiterCounts(result);
  }
  return result;
}

function renderLatex(value, display = false, forceMath = false) {
  const raw = trimOrphanTrailingDelimiter(normalizeFormulaSource(value));
  if (!raw) return "";
  if (/Need (?:final|regenerate)|END ANALYSIS|channel (?:final|switch)/i.test(raw)) {
    return `<span class="latex-source-error" title="Generated text found in formula source">${esc(raw)}</span>`;
  }
  const normalized = normalizeDollarDelimiters(raw);
  if (!hasBalancedDelimiters(normalized)) {
    return `<span class="latex-source-error" title="Unbalanced mathematical delimiters in source data">${esc(raw)}</span>`;
  }
  const hasExplicitDelimiters = /(?<!\\)\\\(|(?<!\\)\\\[/.test(normalized);
  const hasEnvironment = /\\begin\s*\{[^}]+\}/.test(normalized);
  if (hasExplicitDelimiters) return esc(normalized);
  if (hasEnvironment) return esc(`\\[${normalized}\\]`);
  const looksLikeLatex = forceMath
    || /\\[A-Za-z]+|[_^][{A-Za-z0-9\\]|[{}]|[=<>≤≥∈∉⊂⊆⊃⊇±∞∑∏]/.test(normalized);
  if (!looksLikeLatex) return esc(raw);
  return esc(display ? `\\[${normalized}\\]` : `\\(${normalized}\\)`);
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 1800);
}

async function fetchManifest() {
  if (state.manifest) return state.manifest;
  const response = await fetch("data/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`manifest: HTTP ${response.status}`);
  state.manifest = await response.json();
  return state.manifest;
}

async function bootstrap() {
  try {
    await fetchManifest();
    loadQualityIssues();
    loadLayout();
    $("#total-statements").textContent = formatNumber(state.manifest.totals.statements);
    state.subjectId = state.manifest.subject_domains?.[0]?.id || null;
    renderDomainNav();
    bindEvents();
    const route = parseRoute();
    await loadDomain(route.domain || state.manifest.domains[0].id, route.node);
  } catch (error) {
    $("#tree-view").innerHTML = `<div class="empty-statements"><b>Site data could not be loaded</b><span>${esc(error.message)}</span><br><br><span>Open this site through a local HTTP server rather than directly from the file system.</span></div>`;
  }
}

function bindEvents() {
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      if (state.qualityTarget) closeQualityDialog();
      else if (document.body.classList.contains("quality-panel-open")) closeQualityDrawer();
    }
  });
  $("#collapse-button").addEventListener("click", () => {
    state.expanded.clear();
    if (state.data?.roots?.[0]) state.expanded.add(state.data.roots[0].topic_id);
    renderBrowser();
    toast("Topic outline collapsed");
  });
  $("#toggle-library-pane").addEventListener("click", () => togglePane("library"));
  $("#toggle-directory-pane").addEventListener("click", () => togglePane("directory"));
  $("#toggle-detail-pane").addEventListener("click", () => togglePane("detail"));
  bindPaneResizers();
  window.addEventListener("hashchange", async () => {
    const route = parseRoute();
    if (route.domain && route.domain !== state.domainMeta?.id) await loadDomain(route.domain, route.node, false);
    else if (route.node) await navigateToNode(route.node, false, true);
  });
  $("#quality-queue-button").addEventListener("click", openQualityDrawer);
  $("#quality-panel-close").addEventListener("click", closeQualityDrawer);
  $("#quality-export-button").addEventListener("click", exportQualityIssues);
  document.querySelectorAll("[data-submission-view]").forEach(button => button.addEventListener("click", () => {
    openSubmissionView(button.dataset.submissionView);
  }));
  document.querySelectorAll("[data-history-filter]").forEach(button => button.addEventListener("click", () => {
    state.historyFilter = button.dataset.historyFilter;
    renderQualityQueue();
  }));
  $("#quality-form-close").addEventListener("click", closeQualityDialog);
  $("#quality-cancel-button").addEventListener("click", closeQualityDialog);
  $("#quality-form").addEventListener("submit", submitQualityIssue);
}

function loadLayout() {
  let layout = {};
  try {
    layout = JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) || "{}");
  } catch { /* keep defaults */ }
  const widths = [
    ["libraryWidth", "--library-width", 180, 420],
    ["directoryWidth", "--directory-width", 280, 720],
    ["qualityWidth", "--quality-width", 320, 640],
  ];
  widths.forEach(([key, property, minimum, maximum]) => {
    const value = Number(layout[key]);
    if (Number.isFinite(value) && value >= minimum && value <= maximum) {
      document.documentElement.style.setProperty(property, `${value}px`);
    }
  });
  document.body.classList.toggle("library-hidden", Boolean(layout.libraryHidden));
  document.body.classList.toggle("directory-hidden", Boolean(layout.directoryHidden));
  document.body.classList.toggle("detail-hidden", Boolean(layout.detailHidden));
  if (layout.directoryHidden && layout.detailHidden) document.body.classList.remove("detail-hidden");
  updateLayoutControls();
}

function saveLayout() {
  const style = getComputedStyle(document.documentElement);
  const pixels = property => Math.round(parseFloat(style.getPropertyValue(property)) || 0);
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({
    libraryWidth: pixels("--library-width"),
    directoryWidth: pixels("--directory-width"),
    qualityWidth: pixels("--quality-width"),
    libraryHidden: document.body.classList.contains("library-hidden"),
    directoryHidden: document.body.classList.contains("directory-hidden"),
    detailHidden: document.body.classList.contains("detail-hidden"),
  }));
}

function updateLayoutControls() {
  ["library", "directory", "detail"].forEach(name => {
    const visible = !document.body.classList.contains(`${name}-hidden`);
    const button = $(`#toggle-${name}-pane`);
    button.classList.toggle("active", visible);
    button.setAttribute("aria-pressed", String(visible));
    button.title = `${visible ? "Hide" : "Show"} ${PANE_LABELS[name]}`;
  });
}

function setPaneHidden(name, hidden, persist = true) {
  if ((name === "directory" || name === "detail") && hidden) {
    const counterpart = name === "directory" ? "detail" : "directory";
    if (document.body.classList.contains(`${counterpart}-hidden`)) {
      toast("Keep either Outline or Content visible");
      return;
    }
  }
  document.body.classList.toggle(`${name}-hidden`, hidden);
  updateLayoutControls();
  if (persist) saveLayout();
}

function togglePane(name) {
  setPaneHidden(name, !document.body.classList.contains(`${name}-hidden`));
}

function bindPaneResizers() {
  const bind = (selector, widthProperty, calculate, minimum, maximum) => {
    const resizer = $(selector);
    resizer.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      resizer.setPointerCapture(event.pointerId);
      resizer.classList.add("dragging");
      document.body.classList.add("resizing");
      const move = moveEvent => {
        const value = Math.max(minimum, Math.min(maximum(), calculate(moveEvent)));
        document.documentElement.style.setProperty(widthProperty, `${Math.round(value)}px`);
      };
      const finish = () => {
        resizer.classList.remove("dragging");
        document.body.classList.remove("resizing");
        resizer.removeEventListener("pointermove", move);
        resizer.removeEventListener("pointerup", finish);
        resizer.removeEventListener("pointercancel", finish);
        saveLayout();
      };
      resizer.addEventListener("pointermove", move);
      resizer.addEventListener("pointerup", finish);
      resizer.addEventListener("pointercancel", finish);
    });
  };
  bind("#library-resizer", "--library-width", event => event.clientX, 180, () => Math.min(420, window.innerWidth - 720));
  bind("#directory-resizer", "--directory-width", event => event.clientX - $(".workspace").getBoundingClientRect().left, 280, () => Math.max(300, $(".workspace").clientWidth - 340));
  bind("#quality-resizer", "--quality-width", event => window.innerWidth - event.clientX, 320, () => Math.min(640, window.innerWidth - 620));
}

function parseRoute() {
  const raw = decodeURIComponent(location.hash.slice(1));
  const [domain, ...node] = raw.split("/");
  return resolveLegacyRoute(domain, node.join("/") || null);
}

function resolveLegacyRoute(domainId, nodeId = null) {
  const route = state.manifest?.legacy_domain_routes?.[domainId]
    || LEGACY_DOMAIN_ROUTES[domainId];
  let domain = route?.domain_id || domainId;
  const requestedNode = nodeId || route?.default_node_id || null;
  const structuralRoute = (state.manifest?.node_domain_redirects?.[domain] || [])
    .filter(item => requestedNode === item.node_prefix || requestedNode?.startsWith(`${item.node_prefix}.`))
    .sort((left, right) => right.node_prefix.length - left.node_prefix.length)[0];
  if (structuralRoute) domain = structuralRoute.domain_id;
  const redirectedNode = state.manifest?.node_redirects?.[domain]?.[requestedNode]
    || requestedNode;
  return { domain, node: redirectedNode };
}

function versionedDataUrl(path) {
  const url = new URL(path, location.href);
  url.searchParams.set("v", state.manifest.built_at);
  return url;
}

async function fetchPayload(path) {
  const key = versionedDataUrl(path).href;
  if (state.payloadCache.has(key)) return state.payloadCache.get(key);
  if (state.payloadRequests.has(key)) return state.payloadRequests.get(key);
  const request = fetch(key, { cache: "force-cache" }).then(async response => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    const payload = await response.json();
    state.payloadCache.set(key, payload);
    return payload;
  }).finally(() => state.payloadRequests.delete(key));
  state.payloadRequests.set(key, request);
  return request;
}

function domainNavigationItems() {
  const items = state.manifest.domains.map(domain => ({ ...domain, navigation_kind: "domain" }));
  (state.manifest.navigation_shortcuts || []).forEach(shortcut => {
    const position = Math.max(0, Math.min(items.length, Number(shortcut.position || items.length + 1) - 1));
    items.splice(position, 0, { ...shortcut, navigation_kind: "shortcut" });
  });
  return items;
}

function navigationItem(itemId) {
  return domainNavigationItems().find(item => item.id === itemId) || null;
}

function subjectDomains() {
  return state.manifest.subject_domains || [];
}

function activeSubjectDomain() {
  return subjectDomains().find(subject => subject.id === state.subjectId) || subjectDomains()[0] || null;
}

function inferSubjectDomain(collectionId, resolvedDomainId = collectionId) {
  return subjectDomains().find(subject => (
    subject.items.includes(collectionId) || subject.items.includes(resolvedDomainId)
  )) || null;
}

function activeNavigationShortcut() {
  if (!state.selected || !state.domainMeta) return null;
  const pathIds = new Set((state.byId.get(state.selected)?.path || []).map(node => node.topic_id));
  return (state.manifest.navigation_shortcuts || []).find(shortcut => (
    shortcut.domain_id === state.domainMeta.id && pathIds.has(shortcut.default_node_id)
  )) || null;
}

function renderDomainNav() {
  const activeShortcut = activeNavigationShortcut();
  const activeAccent = activeShortcut?.accent || state.domainMeta?.accent || "#2563eb";
  document.documentElement.style.setProperty("--accent", activeAccent);
  document.documentElement.style.setProperty("--accent-soft", `${activeAccent}24`);
  $("#directory-title").textContent = activeShortcut?.short_name || state.domainMeta?.short_name || "Knowledge outline";
  const subject = activeSubjectDomain();
  const items = (subject?.items || []).map(navigationItem).filter(Boolean);
  $("#domain-count").textContent = formatNumber(items.length);
  $("#subject-domain-selector").innerHTML = subjectDomains().map(item => (
    `<option value="${esc(item.id)}" ${item.id === subject?.id ? "selected" : ""}>${esc(item.short_name)}</option>`
  )).join("");
  $("#subject-domain-selector").onchange = () => loadSubjectDomain($("#subject-domain-selector").value);
  $("#domain-nav").innerHTML = items.length ? items.map(item => {
    const isShortcut = item.navigation_kind === "shortcut";
    const active = isShortcut
      ? activeShortcut?.id === item.id
      : item.id === state.domainMeta?.id && !activeShortcut;
    return `
    <button class="domain-button ${active ? "active" : ""}" data-domain="${esc(item.id)}" ${isShortcut ? `data-node="${esc(item.default_node_id)}"` : ""} style="--domain-accent:${item.accent}">
      <span class="domain-swatch"></span>
      <span><b>${esc(item.short_name)}</b><small>${formatNumber(item.stats.topics)} topics · ${formatNumber(item.stats.chapters)} chapters</small></span>
      <em>${formatNumber(item.stats.statements)}</em>
    </button>`;
  }).join("") : `<div class="domain-empty">No subject domains have been published in this major domain yet.</div>`;
  document.querySelectorAll("[data-domain]").forEach(button => button.addEventListener("click", () => loadDomain(button.dataset.domain, button.dataset.node || null)));
  requestAnimationFrame(() => $("#domain-nav .active")?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" }));
}

function loadSubjectDomain(subjectId) {
  const subject = subjectDomains().find(item => item.id === subjectId) || subjectDomains()[0];
  if (!subject) return;
  state.subjectId = subject.id;
  renderDomainNav();
}

async function loadDomain(domainId, requestedNode = null, updateRoute = true) {
  const requestedCollectionId = domainId;
  const resolvedRoute = resolveLegacyRoute(domainId, requestedNode);
  domainId = resolvedRoute.domain;
  requestedNode = resolvedRoute.node;
  const subject = inferSubjectDomain(requestedCollectionId, domainId);
  if (subject) state.subjectId = subject.id;
  const loadToken = ++state.domainLoadToken;
  const navigationToken = ++state.navigationToken;
  const meta = state.manifest.domains.find(item => item.id === domainId) || state.manifest.domains[0];
  state.domainMeta = meta;
  document.documentElement.style.setProperty("--accent", meta.accent);
  document.documentElement.style.setProperty("--accent-soft", `${meta.accent}24`);
  renderDomainNav();
  $("#directory-title").textContent = meta.short_name;
  $("#tree-view").innerHTML = `<div class="loading-state"><span></span><p>Loading ${esc(meta.short_name)}…</p></div>`;
  try {
    let data = state.domainCache.get(meta.id);
    if (!data) {
      data = await fetchPayload(meta.data_url);
      state.domainCache.set(meta.id, data);
    }
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    state.data = data;
    indexTree();
    state.expanded.clear();
    const root = data.roots[0];
    state.expanded.add(root.topic_id);
    renderBrowser();
    if (requestedNode) await ensureRouteLoaded(requestedNode);
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    const target = requestedNode && state.byId.has(requestedNode) ? requestedNode : root.topic_id;
    selectNode(target, updateRoute);
    if (requestedNode) focusTreeNode(target);
  } catch (error) {
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    $("#tree-view").innerHTML = `<div class="empty-statements"><b>Could not load ${esc(meta.short_name)}</b><span>${esc(error.message)}</span></div>`;
  }
}

function indexTree() {
  state.flat = [];
  state.byId = new Map();
  state.parents = new Map();
  const walk = (node, parent = null, path = []) => {
    const entry = { node, parent, path: [...path, node] };
    state.flat.push(entry);
    state.byId.set(node.topic_id, entry);
    if (parent) state.parents.set(node.topic_id, parent.topic_id);
    (node.children || []).forEach(child => walk(child, node, entry.path));
  };
  state.data.roots.forEach(root => walk(root));
}

function renderBrowser() {
  renderTree();
}

function renderTree() {
  const view = $("#tree-view");
  // The selected collection is already named by the directory header. Start
  // the outline at its chapters so a domain title is not shown twice.
  const visibleNodes = state.data.roots.flatMap(root => (
    root.children?.length ? root.children : [root]
  ));
  view.innerHTML = `<ul class="tree-root">${visibleNodes.map(renderTreeNode).join("")}</ul>`;
  bindTreeEvents(view);
}

function renderTreeNode(node) {
  const hasChildren = (node.children || []).length > 0 || Boolean(node.shard_url);
  const open = state.expanded.has(node.topic_id);
  const loading = state.loadingNodes.has(node.topic_id);
  return `<li class="tree-node" data-node-shell="${esc(node.topic_id)}">
    <div class="tree-row ${state.selected === node.topic_id ? "selected" : ""}" data-select-node="${esc(node.topic_id)}" ${loading ? 'aria-busy="true"' : ""}>
      <button class="tree-toggle ${loading ? "loading" : hasChildren ? (open ? "open" : "") : "leaf"}" data-toggle-node="${esc(node.topic_id)}" aria-label="${loading ? "Loading" : open ? "Collapse" : "Expand"}" ${loading ? "disabled" : ""}></button>
      <span class="tree-label"><b title="${esc(node.title)}">${esc(node.title)}</b></span>
      ${node.descendant_statement_count ? `<span class="tree-count">${formatNumber(node.descendant_statement_count)}</span>` : ""}
    </div>
    ${hasChildren && open ? `<ul class="tree-children">${node.children.map(renderTreeNode).join("")}</ul>` : ""}
  </li>`;
}

function bindTreeEvents(root) {
  root.querySelectorAll("[data-toggle-node]").forEach(button => button.addEventListener("click", async event => {
    event.stopPropagation();
    const id = button.dataset.toggleNode;
    if (state.expanded.has(id)) {
      state.expanded.delete(id);
      renderTree();
      return;
    }
    try {
      await ensureRouteLoaded(id);
      state.expanded.add(id);
      renderTree();
    } catch (error) {
      toast(`Could not load topic: ${error.message}`);
    }
  }));
  root.querySelectorAll("[data-select-node]").forEach(row => row.addEventListener("click", async event => {
    if (event.target.closest("[data-toggle-node]")) return;
    await navigateToNode(row.dataset.selectNode);
  }));
}

async function ensureChapterLoaded(chapterId) {
  const entry = state.byId.get(chapterId);
  const chapter = entry?.node;
  if (!chapter?.shard_url || chapter.lazy_loaded) return;
  const domainData = state.data;
  const shardUrl = chapter.shard_url;
  state.loadingNodes.add(chapterId);
  if (state.data === domainData) renderTree();
  try {
    const payload = await fetchPayload(shardUrl);
    if (payload.chapter_id !== chapterId || payload.root?.topic_id !== chapterId) {
      throw new Error(`Unexpected chapter payload for ${chapterId}`);
    }
    Object.assign(chapter, payload.root, {
      shard_url: shardUrl,
      lazy_content: false,
      lazy_loaded: true,
    });
    if (state.data === domainData) indexTree();
  } finally {
    state.loadingNodes.delete(chapterId);
  }
}

async function ensureRouteLoaded(nodeId) {
  const direct = state.byId.get(nodeId)?.node;
  if (direct?.shard_url && !direct.lazy_loaded) {
    await ensureChapterLoaded(nodeId);
    return;
  }
  if (direct) return;
  const chapterId = state.data?.node_routes?.[nodeId];
  if (chapterId) await ensureChapterLoaded(chapterId);
}

async function navigateToNode(nodeId, updateRoute = true, focusTree = false) {
  nodeId = state.manifest?.node_redirects?.[state.domainMeta?.id]?.[nodeId] || nodeId;
  const navigationToken = ++state.navigationToken;
  try {
    await ensureRouteLoaded(nodeId);
    if (navigationToken !== state.navigationToken) return;
    if (!state.byId.has(nodeId)) return;
    selectNode(nodeId, updateRoute);
    if (focusTree) focusTreeNode(nodeId);
  } catch (error) {
    toast(`Could not load topic: ${error.message}`);
  }
}

function focusTreeNode(nodeId) {
  requestAnimationFrame(() => {
    const shell = [...document.querySelectorAll("[data-node-shell]")].find(item => item.dataset.nodeShell === nodeId);
    if (!shell) return;
    shell.scrollIntoView({ behavior: "smooth", block: "center" });
    shell.classList.add("nav-target");
    setTimeout(() => shell.classList.remove("nav-target"), 1150);
  });
}

function revealPath(nodeId) {
  let current = nodeId;
  while (current) { state.expanded.add(current); current = state.parents.get(current); }
}

function selectNode(nodeId, updateRoute = true) {
  if (!state.byId.has(nodeId)) return;
  state.selected = nodeId;
  revealPath(nodeId);
  if (updateRoute) history.pushState(null, "", `#${state.domainMeta.id}/${encodeURIComponent(nodeId)}`);
  renderDetail(nodeId);
  renderTree();
  renderDomainNav();
}

function renderDetail(nodeId) {
  const entry = state.byId.get(nodeId);
  if (!entry) return;
  const node = entry.node;
  const allStatements = node.knowledge_statements || [];
  const statementLimit = state.statementLimits.get(nodeId) || STATEMENT_PAGE_SIZE;
  const statements = allStatements.slice(0, statementLimit);
  const hasMoreStatements = statements.length < allStatements.length;
  const path = entry.path.map(item => `<span>${esc(item.title)}</span>`).join("<i>/</i>");
  const witnesses = node.top_down_textbook_witnesses || [];
  const relationships = renderTopicRelationships(entry);
  const artifacts = entry.parent ? [] : (state.data.artifacts || []);
  const topicRole = node.top_down_role || (allStatements.length ? "" : "This node organizes the knowledge topics below it.");
  $("#detail-panel").innerHTML = `
    <header class="topic-hero">
      <div class="breadcrumbs">${path}</div>
      <h2>${esc(node.title)}</h2>
      ${topicRole ? `<p class="topic-role">${esc(topicRole)}</p>` : ""}
      <div class="topic-actions"><button class="review-button" type="button" data-quality-target-type="topic" data-quality-target-id="${esc(node.topic_id)}">Report topic issue</button></div>
    </header>
    <div class="detail-body">
      ${relationships}
      ${renderDomainArtifacts(artifacts)}
      <div class="section-heading"><h3>Knowledge statements</h3><span>${statements.length} / ${allStatements.length} records</span></div>
      ${statements.length ? `<div class="statement-list">${statements.map((statement, index) => renderStatement(statement, index)).join("")}</div>` : `
        <div class="empty-statements"><b>${allStatements.length ? "No statements match this filter" : "Structural topic"}</b><span>${allStatements.length ? "Choose another statement type above." : `Concrete knowledge is stored in ${formatNumber(node.descendant_statement_count)} descendant statements.`}</span></div>`}
      ${hasMoreStatements ? `<button class="load-more-statements" type="button" data-load-more-statements="${esc(nodeId)}">Show ${Math.min(STATEMENT_PAGE_SIZE, allStatements.length - statements.length)} more statements</button>` : ""}
      ${witnesses.length ? `<section class="witness-section"><div class="section-heading"><h3>Source references</h3><span>${witnesses.length} references</span></div><div class="source-list">${witnesses.map(renderWitness).join("")}</div></section>` : ""}
    </div>`;
  $("#detail-panel").scrollTop = 0;
  $("#detail-panel").querySelectorAll("[data-related-node]").forEach(button => {
    button.addEventListener("click", () => navigateToNode(button.dataset.relatedNode, true, true));
  });
  $("#detail-panel").querySelectorAll("[data-prerequisite-node]").forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      const nodeId = link.dataset.prerequisiteNode;
      const domainId = link.dataset.prerequisiteDomain;
      if (domainId === state.domainMeta.id) {
        navigateToNode(nodeId, true, true);
      } else {
        loadDomain(domainId, nodeId);
      }
    });
  });
  $("#detail-panel").querySelectorAll("[data-quality-target-type]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      openQualityDialog(button.dataset.qualityTargetType, button.dataset.qualityTargetId);
    });
  });
  $("#detail-panel").querySelector("[data-load-more-statements]")?.addEventListener("click", () => {
    state.statementLimits.set(nodeId, statementLimit + STATEMENT_PAGE_SIZE);
    renderDetail(nodeId);
  });
  typesetMath($("#detail-panel"));
}

function renderDomainArtifacts(artifacts) {
  if (!artifacts.length) return "";
  return `<section class="artifact-section">
    <div class="section-heading"><h3>Domain graph artifacts</h3><span>${artifacts.length} files</span></div>
    <div class="artifact-grid">${artifacts.map(artifact => {
      const stats = Object.entries(artifact.stats || {}).map(([key, value]) => (
        `<span>${esc(titleCase(key))}: <b>${formatNumber(value)}</b></span>`
      )).join("");
      return `<a class="artifact-card" href="${esc(artifact.url)}" target="_blank" rel="noopener">
        <small>${esc(titleCase(artifact.kind))}</small>
        <b>${esc(artifact.title)}</b>
        <p>${esc(artifact.description)}</p>
        ${stats ? `<div>${stats}</div>` : ""}
      </a>`;
    }).join("")}</div>
  </section>`;
}

function renderTopicRelationships(entry) {
  const parent = entry.parent;
  const children = entry.node.children || [];
  if (!parent && !children.length) return "";
  const groups = [];
  if (parent) {
    groups.push(`
      <section class="relation-group parent-relation">
        <div class="relation-heading"><h3>Parent topic</h3></div>
        <button class="relation-card" type="button" data-related-node="${esc(parent.topic_id)}">
          <b>${esc(parent.title)}</b><span aria-hidden="true">↑</span>
        </button>
      </section>`);
  }
  if (children.length) {
    groups.push(`
      <section class="relation-group child-relations">
        <div class="relation-heading"><h3>Child topics</h3><small>${children.length}</small></div>
        <div class="relation-list">
          ${children.map(child => `
            <button class="relation-card" type="button" data-related-node="${esc(child.topic_id)}">
              <b>${esc(child.title)}</b><span aria-hidden="true">→</span>
            </button>`).join("")}
        </div>
      </section>`);
  }
  return `<div class="topic-relations">${groups.join("")}</div>`;
}

function arrayValues(value) {
  if (Array.isArray(value)) return value.filter(item => item !== null && item !== undefined && String(item).trim());
  if (value === null || value === undefined || String(value).trim() === "") return [];
  return [value];
}

function renderStatementSource(source) {
  const title = source.source_title || source.source_id || source.source_graph_id || "Source evidence";
  const locator = source.locator || source.source_locator || "No item-level locator supplied";
  const itemId = source.source_item_id || source.statement_id || "";
  const grounding = source.fulltext_span_verified === true
    ? "full-text span verified"
    : source.fulltext_span_verified === false
      ? "extraction grounded; full-text span not verified"
      : "grounding status not recorded";
  return `<div class="statement-source-item">
    <b>${esc(title)}</b>
    <span>${esc(locator)}</span>
    <small>${itemId ? `<code>${esc(itemId)}</code> · ` : ""}${esc(grounding)}</small>
  </div>`;
}

function renderVariantDimensions(dimensions) {
  if (!dimensions || typeof dimensions !== "object" || Array.isArray(dimensions)) return "";
  const groups = Object.entries(dimensions).filter(([, value]) => arrayValues(value).length);
  if (!groups.length) return "";
  return `<div class="meta-block full"><label>Variant regime</label><div class="variant-grid">${groups.map(([key, values]) => `
    <section><b>${esc(titleCase(key))}</b><ul>${arrayValues(values).map(value => `<li>${esc(value)}</li>`).join("")}</ul></section>`).join("")}</div></div>`;
}

function renderGraphRelations(relations) {
  if (!relations || typeof relations !== "object" || Array.isArray(relations)) return "";
  const dependencies = relations.depends_on || [];
  const unresolved = relations.depends_on_unresolved || [];
  const mentions = relations.mentions || [];
  if (!dependencies.length && !unresolved.length && !mentions.length) return "";
  return `<div class="meta-block full graph-relations"><label>Extracted graph relations</label>
    ${dependencies.length ? `<section><b>Depends on</b><ul>${dependencies.map(item => (
      `<li>${esc(item.label || item.target_id)} <code>${esc(item.target_id)}</code>${item.document_title ? `<span>${esc(item.document_title)}</span>` : ""}</li>`
    )).join("")}</ul></section>` : ""}
    ${unresolved.length ? `<section class="unresolved"><b>Unresolved dependency labels</b><ul>${unresolved.map(item => (
      `<li>${esc(item.label || item.target_id)} <code>${esc(item.resolution_status || "unresolved")}</code></li>`
    )).join("")}</ul></section>` : ""}
    ${mentions.length ? `<section><b>Mentioned PIC/Ricci-flow terms</b><div class="term-chips">${mentions.map(item => (
      `<span>${esc(item.name || item.target_id)}${item.count ? ` · ${formatNumber(item.count)}` : ""}</span>`
    )).join("")}</div></section>` : ""}
  </div>`;
}

function renderAlgorithmContract(contract) {
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) return "";
  const list = (values, renderer = value => esc(value)) => arrayValues(values).length
    ? `<ul>${arrayValues(values).map(value => `<li>${renderer(value)}</li>`).join("")}</ul>`
    : "";
  const steps = Array.isArray(contract.steps) ? contract.steps.filter(step => step && typeof step === "object") : [];
  const branches = Array.isArray(contract.branches) ? contract.branches.filter(branch => branch && typeof branch === "object") : [];
  const initialization = Array.isArray(contract.initialization) ? contract.initialization.filter(item => item && typeof item === "object") : [];
  const quantities = Array.isArray(contract.quantities) ? contract.quantities.filter(item => item && typeof item === "object") : [];
  const terminations = Array.isArray(contract.termination) ? contract.termination.filter(item => item && typeof item === "object") : [];
  const outputs = Array.isArray(contract.outputs) ? contract.outputs.filter(item => item && typeof item === "object") : [];
  const objectList = (items, valueKey, labelKey = "label") => items.length
    ? `<ul class="algorithm-contract-list">${items.map(item => `<li>${item[labelKey] ? `<b>${esc(item[labelKey])}</b>` : ""}${item[valueKey] ? `<span class="latex-value">${renderLatex(item[valueKey])}</span>` : ""}${item.note ? `<small>${esc(item.note)}</small>` : ""}</li>`).join("")}</ul>`
    : "";
  return `<details class="algorithm-contract">
    <summary><b>Algorithm contract</b><span>${esc(contract.schema_version || "structured procedure")}</span></summary>
    <div class="algorithm-contract-body">
      ${arrayValues(contract.inputs).length ? `<div class="meta-block full"><label>Inputs</label>${list(contract.inputs)}</div>` : ""}
      ${arrayValues(contract.assumptions).length ? `<div class="meta-block full"><label>Assumptions</label>${list(contract.assumptions, value => renderLatex(value))}</div>` : ""}
      ${initialization.length ? `<div class="meta-block full"><label>Initialization</label>${objectList(initialization, "value_latex")}</div>` : ""}
      ${quantities.length ? `<div class="meta-block full"><label>Quantities</label>${objectList(quantities, "formula_latex")}</div>` : ""}
      ${steps.length ? `<div class="meta-block full"><label>Steps</label><ol class="algorithm-steps">${steps.map(step => `<li data-step-id="${esc(step.step_id || "")}"><div><code>${esc(step.step_id || "unlabelled")}</code><b>${esc(step.title || "Step")}</b><span class="step-target">→ ${esc(step.next_step || "")}</span></div>${step.action_latex ? `<div class="latex-value">${renderLatex(step.action_latex)}</div>` : ""}</li>`).join("")}</ol></div>` : ""}
      ${branches.length ? `<div class="meta-block full"><label>Branches</label><ul class="algorithm-branches">${branches.map(branch => `<li>${branch.condition_latex ? `<div class="latex-value"><b>If</b> ${renderLatex(branch.condition_latex)}</div>` : ""}${branch.action_latex ? `<div class="latex-value"><b>Then</b> ${renderLatex(branch.action_latex)}</div>` : ""}<span class="step-target">→ ${esc(branch.next_step || "")}</span></li>`).join("")}</ul></div>` : ""}
      ${terminations.length ? `<div class="meta-block full"><label>Termination</label><ul class="algorithm-branches">${terminations.map(item => `<li>${item.condition_latex ? `<div class="latex-value"><b>When</b> ${renderLatex(item.condition_latex)}</div>` : ""}<span>${esc(item.action || "Return")}</span></li>`).join("")}</ul></div>` : ""}
      ${outputs.length ? `<div class="meta-block full"><label>Outputs</label>${objectList(outputs, "value_latex")}</div>` : ""}
      ${arrayValues(contract.dependencies).length ? `<div class="meta-block full"><label>Dependencies</label>${list(contract.dependencies)}</div>` : ""}
      ${arrayValues(contract.source_boundaries).length ? `<div class="meta-block full boundary-block"><label>Source boundaries</label>${list(contract.source_boundaries)}</div>` : ""}
    </div>
  </details>`;
}

function renderStatement(statement, index) {
  const assumptions = statement.assumptions_latex || [];
  const notation = statement.notation || [];
  const conclusion = statement.conclusion && typeof statement.conclusion === "object" && !Array.isArray(statement.conclusion)
    ? statement.conclusion
    : {};
  const conclusionLatex = statement.conclusion_latex || conclusion.conclusion_latex || "";
  const sources = statement.source_refs?.length ? statement.source_refs : (statement.source_witnesses || []);
  const boundaryNotes = arrayValues(statement.boundary_notes);
  const equivalentFormulations = arrayValues(statement.equivalent_formulations_latex);
  const relations = arrayValues(statement.relations);
  const rateClass = conclusion.rate_class && !["none", "not applicable"].includes(String(conclusion.rate_class).toLowerCase())
    ? conclusion.rate_class
    : "";
  const badges = [
    statement.content_kind ? { value: statement.content_kind, kind: "kind" } : null,
    rateClass ? { value: rateClass, kind: "rate" } : null,
    statement.intermediate_metadata?.partial_run ? { value: "partial run", kind: "partial" } : null,
  ].filter(Boolean);
  return `<details class="statement-card" id="stmt-${esc(statement.id)}" ${index === 0 ? "open" : ""}>
    <summary>
      <b>${esc(statement.title || statement.statement_title || "Untitled statement")}</b>
      <span class="statement-badges">${badges.map(badge => `<em class="statement-badge ${badge.kind}">${esc(titleCase(badge.value))}</em>`).join("")}</span>
    </summary>
    <div class="statement-content">
      <div class="statement-tools"><button class="review-button" type="button" data-quality-target-type="statement" data-quality-target-id="${esc(statement.id)}">Report statement issue</button></div>
      ${statement.statement_plain ? `<p class="plain-statement">${esc(statement.statement_plain)}</p>` : ""}
      ${statement.statement_latex ? `<div class="formal-block">${renderLatex(statement.statement_latex, true)}</div>` : ""}
      ${renderAlgorithmContract(statement.algorithm_contract)}
      ${statement.proof_latex ? `<details class="source-proof">
        <summary><b>Source proof</b><span>${statement.proof_length ? `${formatNumber(statement.proof_length)} characters` : "extracted proof text"}</span></summary>
        <div class="formal-block">${renderLatex(statement.proof_latex, true)}</div>
      </details>` : ""}
      <div class="statement-meta">
        ${assumptions.length ? `<div class="meta-block full"><label>Assumptions</label><ul class="latex-list">${assumptions.map(value => `<li>${renderLatex(value)}</li>`).join("")}</ul></div>` : ""}
        ${conclusionLatex ? `<div class="meta-block full"><label>Conclusion</label><div class="latex-value">${renderLatex(conclusionLatex)}</div></div>` : ""}
        ${conclusion.target ? `<div class="meta-block full"><label>Convergence target</label><p>${esc(conclusion.target)}</p></div>` : ""}
        ${arrayValues(conclusion.convergence_objects).length ? `<div class="meta-block full"><label>Convergence objects</label><ul>${arrayValues(conclusion.convergence_objects).map(value => `<li>${esc(value)}</li>`).join("")}</ul></div>` : ""}
        ${conclusion.nonasymptotic_bound_latex ? `<div class="meta-block full"><label>Nonasymptotic bound</label><div class="latex-value">${renderLatex(conclusion.nonasymptotic_bound_latex)}</div></div>` : ""}
        ${conclusion.epsilon_complexity_latex ? `<div class="meta-block full"><label>Epsilon complexity</label><div class="latex-value">${renderLatex(conclusion.epsilon_complexity_latex)}</div></div>` : ""}
        ${["sequence_scope", "topology_or_mode", "probability_mode", "locality", "rate_class"].map(key => conclusion[key] ? `<div class="meta-block"><label>${esc(titleCase(key))}</label><p>${esc(titleCase(conclusion[key]))}</p></div>` : "").join("")}
        ${renderVariantDimensions(statement.variant_dimensions)}
        ${equivalentFormulations.length ? `<div class="meta-block full"><label>Equivalent formulations</label><ul class="latex-list">${equivalentFormulations.map(value => `<li>${renderLatex(value)}</li>`).join("")}</ul></div>` : ""}
        ${boundaryNotes.length ? `<div class="meta-block full boundary-block"><label>Boundary and limitation notes</label><ul>${boundaryNotes.map(value => `<li>${esc(value)}</li>`).join("")}</ul></div>` : ""}
        ${relations.length ? `<div class="meta-block full"><label>Variant relations</label><div class="variant-relations">${relations.map(relation => `<p><b>${esc(titleCase(relation.relation || "related"))}</b> <code>${esc(relation.target_variant_id || relation.target_local_variant_id || "")}</code>${relation.rationale ? `<span>${esc(relation.rationale)}</span>` : ""}</p>`).join("")}</div></div>` : ""}
        ${statement.intermediate_metadata?.reason ? `<div class="meta-block full"><label>Deferred reason</label><p>${esc(statement.intermediate_metadata.reason)}</p></div>` : ""}
        ${statement.intermediate_metadata?.review_comment ? `<div class="meta-block full"><label>Review comment</label><p>${esc(statement.intermediate_metadata.review_comment)}</p></div>` : ""}
        ${statement.prerequisite_node_ids?.length ? `<div class="meta-block full"><label>Prerequisites</label><p class="prerequisite-links">${statement.prerequisite_node_ids.map(renderPrerequisite).join("<span>·</span>")}</p></div>` : ""}
        ${notation.length ? `<div class="meta-block full"><label>Notation</label><ul class="latex-list">${notation.map(item => `<li><span class="notation-symbol">${renderLatex(item.symbol_latex, false, true)}</span><span>— ${esc(item.meaning)}</span></li>`).join("")}</ul></div>` : ""}
        ${sources.length ? `<div class="meta-block full"><label>Statement evidence</label><div class="statement-source-list">${sources.map(renderStatementSource).join("")}</div></div>` : ""}
        ${renderGraphRelations(statement.graph_relations)}
        <div class="meta-block full"><label>Statement ID</label><p><code>${esc(statement.id)}</code></p></div>
      </div>
    </div>
  </details>`;
}

function renderPrerequisite(nodeId) {
  const prefix = String(nodeId).split(".")[0];
  const domainByPrefix = {
    A02: "convex_analysis",
    A03: "variational_analysis",
    A04: "nonlinear_programming",
    A05: "first_order_methods",
    A06: "nonsmooth_optimization",
    A07: "specialized_continuous_methods",
    A08: "convex_programming",
    A09: "linear_programming",
    A10: "conic_optimization",
    A11: "quadratic_optimization",
    A12: "integer_mixed_integer_optimization",
    A13: "combinatorial_optimization",
    A14: "constraint_logic_optimization",
    A15: "global_optimization",
    A16: "optimization_under_uncertainty",
  };
  const domainId = domainByPrefix[prefix];
  if (!domainId) return `<code>${esc(nodeId)}</code>`;
  const href = `#${domainId}/${encodeURIComponent(nodeId)}`;
  return `<a href="${esc(href)}" data-prerequisite-node="${esc(nodeId)}" data-prerequisite-domain="${esc(domainId)}" title="Open prerequisite">${esc(nodeId)}</a>`;
}

function renderWitness(witness) {
  const title = witness.source_title || witness.source_query || witness.source_graph_id || "Source witness";
  const locator = witness.locator || witness.source_locator || witness.matched_excerpt || "No locator supplied";
  const status = witness.locator_traceability?.status || witness.evidence_role || witness.validation_scope || "";
  return `<div class="source-item"><b>${esc(title)}</b><span>${esc(locator)}${status ? ` · ${esc(status)}` : ""}</span></div>`;
}

let mathTypesetQueue = Promise.resolve();
let mathJaxReadyPromise = null;

function waitForMathJax(timeoutMs = 12000) {
  if (window.MathJax?.startup?.promise) {
    return window.MathJax.startup.promise.then(() => window.MathJax).catch(() => null);
  }
  if (mathJaxReadyPromise) return mathJaxReadyPromise;
  const pending = new Promise(resolve => {
    const deadline = Date.now() + timeoutMs;
    const probe = () => {
      if (window.MathJax?.startup?.promise) {
        return window.MathJax.startup.promise.then(() => resolve(window.MathJax), () => resolve(null));
      }
      if (Date.now() >= deadline) return resolve(null);
      setTimeout(probe, 50);
    };
    probe();
  });
  const wrapped = pending.then(mathJax => {
    if (!mathJax && mathJaxReadyPromise === wrapped) mathJaxReadyPromise = null;
    return mathJax;
  });
  mathJaxReadyPromise = wrapped;
  return wrapped;
}

function typesetMath(container) {
  if (!container) return;
  mathTypesetQueue = mathTypesetQueue
    .then(() => waitForMathJax())
    .then(mathJax => {
      if (!container.isConnected || !mathJax?.typesetPromise) return;
      // Clear stale MathJax nodes when a caller reuses a mounted container.
      mathJax.typesetClear?.([container]);
      return mathJax.typesetPromise([container]);
    })
    .catch(error => console.warn("Math rendering failed", error));
}

function loadQualityIssues() {
  try {
    const raw = localStorage.getItem(SUBMISSIONS_STORAGE_KEY) || localStorage.getItem(QUALITY_STORAGE_KEY) || "[]";
    const stored = JSON.parse(raw);
    let migrated = false;
    state.qualityIssues = Array.isArray(stored) ? stored.map(issue => {
      if (!issue.remote_status) {
        issue = { ...issue, remote_status: "pending" };
        migrated = true;
      }
      const route = resolveLegacyRoute(issue.domain_id, issue.topic_id);
      if (route.domain === issue.domain_id && route.node === issue.topic_id) return issue;
      migrated = true;
      const updated = { ...issue, domain_id: route.domain, topic_id: route.node };
      if (issue.target_type === "topic" && issue.target_id === issue.topic_id) {
        updated.target_id = route.node;
      }
      updated.page_hash = route.node
        ? `#${route.domain}/${encodeURIComponent(route.node)}`
        : `#${route.domain}`;
      return updated;
    }) : [];
    if (migrated || !localStorage.getItem(SUBMISSIONS_STORAGE_KEY)) saveQualityIssues();
  } catch {
    state.qualityIssues = [];
  }
  loadSubmissionHistory();
  updateQualityCount();
  retryRemoteSubmissions();
}

function saveQualityIssues() {
  localStorage.setItem(SUBMISSIONS_STORAGE_KEY, JSON.stringify(state.qualityIssues));
  updateQualityCount();
}

function loadSubmissionHistory() {
  try {
    const stored = JSON.parse(localStorage.getItem(SUBMISSION_HISTORY_STORAGE_KEY) || "[]");
    state.submissionHistory = Array.isArray(stored) ? stored : [];
  } catch {
    state.submissionHistory = [];
  }
  if (!state.submissionHistory.length && state.qualityIssues.length) {
    state.submissionHistory = state.qualityIssues.map(issue => ({
      event_id: `EV-${issue.issue_id}`,
      issue_id: issue.issue_id,
      action: "imported",
      version: issue.version || 1,
      created_at: issue.created_at,
      snapshot: { note: issue.note, severity: issue.severity, issue_type: issue.issue_type, status: issue.status },
    }));
    saveSubmissionHistory();
  }
}

function saveSubmissionHistory() {
  localStorage.setItem(SUBMISSION_HISTORY_STORAGE_KEY, JSON.stringify(state.submissionHistory));
}

function appendSubmissionHistory(issue, action, snapshot = {}) {
  const event = {
    event_id: `EV-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
    issue_id: issue.issue_id,
    action,
    version: issue.version || 1,
    created_at: new Date().toISOString(),
    snapshot: { note: issue.note, severity: issue.severity, issue_type: issue.issue_type, status: issue.status, ...snapshot },
  };
  state.submissionHistory.unshift(event);
  saveSubmissionHistory();
  return event;
}

async function sendSubmissionEvent(issue, event) {
  if (!SUBMISSION_ENDPOINT) return false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SUBMISSION_TIMEOUT_MS);
  const fields = {
    _subject: `ReasAtlas ${event.action}: ${issue.issue_id}`,
    source: "reasatlas-web",
    site_snapshot: state.manifest?.snapshot_version || "unknown",
    origin: location.origin,
    event_id: event.event_id,
    action: event.action,
    event_version: event.version || 1,
    issue_id: issue.issue_id,
    status: issue.status,
    severity: issue.severity,
    issue_type: issue.issue_type,
    issue_type_label: titleCase(issue.issue_type),
    reason: issue.note,
    note: issue.note,
    domain_id: issue.domain_id,
    topic_id: issue.topic_id,
    target_type: issue.target_type,
    target_id: issue.target_id,
    target_title: issue.target_title,
    target_path: (issue.path || []).join(" / "),
    target_context: JSON.stringify(issue.snapshot || {}),
    page_hash: issue.page_hash,
    created_at: issue.created_at,
    updated_at: issue.updated_at || "",
    event_snapshot: JSON.stringify(event.snapshot),
    history_events: JSON.stringify(
      state.submissionHistory.filter(item => item.issue_id === issue.issue_id).slice(0, 50)
    ),
  };
  const formData = new FormData();
  Object.entries(fields).forEach(([key, value]) => formData.append(key, String(value ?? "")));
  try {
    const response = await fetch(SUBMISSION_ENDPOINT, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: formData,
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Formspree HTTP ${response.status}`);
    return true;
  } catch (error) {
    console.warn("Submission remote sync failed; local copy retained", error);
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function queueSubmissionEvent(issue, event) {
  issue.remote_status = "sending";
  issue.remote_last_attempt_at = new Date().toISOString();
  saveQualityIssues();
  void sendSubmissionEvent(issue, event).then(sent => {
    issue.remote_status = sent ? "sent" : "failed";
    issue.remote_last_attempt_at = new Date().toISOString();
    saveQualityIssues();
  });
}

function retryRemoteSubmissions() {
  const now = Date.now();
  state.qualityIssues
    .filter(issue => {
      if (issue.remote_status === "pending" || issue.remote_status === "failed") return true;
      if (issue.remote_status !== "sending") return false;
      const attemptedAt = Date.parse(issue.remote_last_attempt_at || "");
      return !Number.isFinite(attemptedAt) || now - attemptedAt > 60000;
    })
    .forEach((issue, index) => {
      const event = {
        event_id: `EV-RETRY-${issue.issue_id}-${issue.version || 1}`,
        issue_id: issue.issue_id,
        action: "retry",
        version: issue.version || 1,
        created_at: new Date().toISOString(),
        snapshot: { note: issue.note, severity: issue.severity, issue_type: issue.issue_type, status: issue.status },
      };
      setTimeout(() => queueSubmissionEvent(issue, event), index * 250);
    });
}

function updateQualityCount() {
  const issues = state.qualityIssues;
  const openCount = issues.filter(issue => issue.status !== "resolved").length;
  const resolvedCount = issues.length - openCount;
  $("#quality-open-count").textContent = formatNumber(issues.length);
  $("#history-total-count").textContent = formatNumber(issues.length);
  $("#history-open-count").textContent = formatNumber(openCount);
  $("#history-resolved-count").textContent = formatNumber(resolvedCount);
}

function openQualityDialog(targetType, targetId) {
  const entry = state.byId.get(state.selected);
  if (!entry) return;
  let target;
  if (targetType === "topic") {
    const topicEntry = state.byId.get(targetId);
    if (!topicEntry) return;
    target = {
      target_type: "topic",
      target_id: targetId,
      target_title: topicEntry.node.title,
      topic_id: targetId,
      path: topicEntry.path.map(item => item.title),
      snapshot: {
        display_number: topicEntry.node.display_number,
        top_down_role: topicEntry.node.top_down_role,
        child_topic_ids: (topicEntry.node.children || []).map(child => child.topic_id),
        child_titles: (topicEntry.node.children || []).map(child => child.title),
      },
    };
  } else {
    const statement = (entry.node.knowledge_statements || []).find(item => item.id === targetId);
    if (!statement) return;
    target = {
      target_type: "statement",
      target_id: targetId,
      target_title: statement.title,
      topic_id: entry.node.topic_id,
      path: entry.path.map(item => item.title),
      snapshot: {
        statement_plain: statement.statement_plain,
        statement_latex: statement.statement_latex,
        assumptions_latex: statement.assumptions_latex || [],
        conclusion_latex: statement.conclusion_latex,
        prerequisite_node_ids: statement.prerequisite_node_ids || [],
        pipeline_stage: statement.intermediate_metadata?.stage || "official_tree",
      },
    };
  }
  state.qualityTarget = { ...target, domain_id: state.domainMeta.id };
  state.editingIssueId = null;
  $("#quality-target").innerHTML = `<b>${esc(target.target_title)}</b><span>${esc(target.path.join(" / "))}</span>`;
  $("#quality-issue-type").innerHTML = QUALITY_TYPES[targetType].map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("");
  $("#quality-severity").value = "medium";
  $("#quality-note").value = "";
  state.layoutBeforeAnnotation = {
    libraryHidden: document.body.classList.contains("library-hidden"),
  };
  setPaneHidden("library", true, false);
  openQualityPanel("form");
  setTimeout(() => $("#quality-note").focus(), 20);
}

function openEditQualityDialog(issueId) {
  const issue = state.qualityIssues.find(item => item.issue_id === issueId);
  if (!issue) return;
  state.editingIssueId = issueId;
  state.qualityTarget = issue;
  $("#quality-target").innerHTML = `<b>${esc(issue.target_title)}</b><span>${esc((issue.path || []).join(" / "))}</span>`;
  $("#quality-issue-type").innerHTML = QUALITY_TYPES[issue.target_type].map(([value, label]) => `<option value="${value}" ${value === issue.issue_type ? "selected" : ""}>${esc(label)}</option>`).join("");
  $("#quality-severity").value = issue.severity || "medium";
  $("#quality-note").value = issue.note || "";
  openQualityPanel("form");
  setTimeout(() => $("#quality-note").focus(), 20);
}

function closeQualityDialog() {
  state.qualityTarget = null;
  state.editingIssueId = null;
  closeQualityPanel();
  restoreLayoutAfterAnnotation();
}

function submitQualityIssue(event) {
  event.preventDefault();
  if (!state.qualityTarget) return;
  const note = $("#quality-note").value.trim();
  if (!note) return;
  if (state.editingIssueId) {
    const issue = state.qualityIssues.find(item => item.issue_id === state.editingIssueId);
    if (!issue) return;
    const previous = { note: issue.note, severity: issue.severity, issue_type: issue.issue_type };
    issue.note = note;
    issue.severity = $("#quality-severity").value;
    issue.issue_type = $("#quality-issue-type").value;
    issue.version = (issue.version || 1) + 1;
    issue.updated_at = new Date().toISOString();
    issue.remote_status = "pending";
    saveQualityIssues();
    const submissionEvent = appendSubmissionHistory(issue, "edited", { previous });
    queueSubmissionEvent(issue, submissionEvent);
    closeQualityDialog();
    toast("Submission updated; the previous version remains in edit history");
    return;
  }
  const issueId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const issue = {
    schema_version: "optistacks-quality-issue-v1",
    issue_id: `QC-${issueId}`,
    status: "open",
    severity: $("#quality-severity").value,
    issue_type: $("#quality-issue-type").value,
    note,
    created_at: new Date().toISOString(),
    page_hash: location.hash,
    ...state.qualityTarget,
    version: 1,
    remote_status: "pending",
  };
  state.qualityIssues.unshift(issue);
  saveQualityIssues();
  const submissionEvent = appendSubmissionHistory(issue, "submitted");
  queueSubmissionEvent(issue, submissionEvent);
  closeQualityDialog();
  toast("Correction submitted and added to your history");
}

function openQualityDrawer() {
  if (state.qualityTarget) {
    closeQualityDialog();
    return;
  }
  renderQualityQueue();
  if (document.body.classList.contains("quality-panel-open") && !$("#quality-queue-view").hidden) {
    closeQualityDrawer();
    return;
  }
  openQualityPanel("queue");
}

function closeQualityDrawer() {
  if (state.qualityTarget) {
    closeQualityDialog();
    return;
  }
  closeQualityPanel();
}

function openQualityPanel(view) {
  const showForm = view === "form";
  state.submissionView = view === "history" ? "history" : "queue";
  $("#quality-queue-view").hidden = showForm;
  $("#quality-history-view").hidden = state.submissionView !== "history" || showForm;
  $("#quality-form-view").hidden = !showForm;
  document.body.classList.add("quality-panel-open");
  $("#quality-panel").setAttribute("aria-hidden", "false");
  $("#quality-queue-button").setAttribute("aria-pressed", "true");
}

function closeQualityPanel() {
  document.body.classList.remove("quality-panel-open");
  $("#quality-panel").setAttribute("aria-hidden", "true");
  $("#quality-queue-button").setAttribute("aria-pressed", "false");
}

function openSubmissionView(view) {
  if (view === "history") renderSubmissionHistory();
  else renderQualityQueue();
  openQualityPanel(view);
  document.querySelectorAll("[data-submission-view]").forEach(button => {
    const active = button.dataset.submissionView === state.submissionView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function restoreLayoutAfterAnnotation() {
  if (!state.layoutBeforeAnnotation) return;
  setPaneHidden("library", state.layoutBeforeAnnotation.libraryHidden, false);
  state.layoutBeforeAnnotation = null;
}

function renderQualityQueue() {
  const allIssues = state.qualityIssues;
  const issues = allIssues.filter(issue => {
    if (state.historyFilter === "open") return issue.status !== "resolved";
    if (state.historyFilter === "resolved") return issue.status === "resolved";
    return true;
  });
  updateQualityCount();
  document.querySelectorAll("[data-history-filter]").forEach(button => {
    const active = button.dataset.historyFilter === state.historyFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const filterLabels = { all: "All submissions", open: "Open submissions", resolved: "Resolved submissions" };
  $("#history-result-label").textContent = `${filterLabels[state.historyFilter]} · ${formatNumber(issues.length)}`;
  $("#quality-issue-list").innerHTML = issues.length ? issues.map(issue => `
    <article class="quality-issue-card ${issue.status === "resolved" ? "resolved" : ""}">
      <div class="quality-issue-top"><span class="severity-badge">${esc(issue.severity)} priority</span><span class="submission-status ${issue.status === "resolved" ? "resolved" : "open"}">${issue.status === "resolved" ? "Resolved" : "Open"}</span></div>
      <h3>${esc(issue.target_title)}</h3>
      <div class="quality-issue-meta"><span>${esc(titleCase(issue.issue_type))}</span><time datetime="${esc(issue.created_at)}">${esc(formatSubmissionDate(issue.created_at))}</time></div>
      <p>${esc(issue.note)}</p>
      <div class="quality-card-actions">
        <button type="button" data-quality-goto="${esc(issue.issue_id)}">Open target</button>
        <button type="button" data-quality-edit="${esc(issue.issue_id)}">Edit</button>
        <button type="button" data-quality-toggle="${esc(issue.issue_id)}">${issue.status === "resolved" ? "Mark open" : "Mark resolved"}</button>
      </div>
    </article>`).join("") : `<div class="quality-empty"><b>No ${state.historyFilter === "all" ? "" : `${esc(state.historyFilter)} `}submissions yet.</b><br>Use “Report topic issue” or “Report statement issue” while exploring the atlas.</div>`;
  $("#quality-issue-list").querySelectorAll("[data-quality-goto]").forEach(button => {
    button.addEventListener("click", () => navigateToQualityTarget(button.dataset.qualityGoto));
  });
  $("#quality-issue-list").querySelectorAll("[data-quality-toggle]").forEach(button => {
    button.addEventListener("click", () => toggleQualityIssue(button.dataset.qualityToggle));
  });
  $("#quality-issue-list").querySelectorAll("[data-quality-edit]").forEach(button => {
    button.addEventListener("click", () => openEditQualityDialog(button.dataset.qualityEdit));
  });
}

function renderSubmissionHistory() {
  const list = $("#submission-history-list");
  list.innerHTML = state.submissionHistory.length ? state.submissionHistory.map(event => `
    <article class="submission-history-card">
      <div class="quality-issue-top"><span class="severity-badge">${esc(titleCase(event.action))}</span><time>${esc(formatSubmissionDate(event.created_at))}</time></div>
      <h3>${esc(event.issue_id)}</h3>
      <div class="quality-issue-meta"><span>Version ${formatNumber(event.version || 1)}</span><span>${esc(event.snapshot?.status || "")}</span></div>
      <p>${esc(event.snapshot?.note || "No note snapshot")}</p>
    </article>`).join("") : `<div class="quality-empty"><b>No edit history yet.</b><br>Submitted corrections and later changes will appear here.</div>`;
}

function formatSubmissionDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function toggleQualityIssue(issueId) {
  const issue = state.qualityIssues.find(item => item.issue_id === issueId);
  if (!issue) return;
  issue.status = issue.status === "resolved" ? "open" : "resolved";
  issue.updated_at = new Date().toISOString();
  issue.remote_status = "pending";
  saveQualityIssues();
  const event = appendSubmissionHistory(issue, "status_changed");
  queueSubmissionEvent(issue, event);
  renderQualityQueue();
}

async function navigateToQualityTarget(issueId) {
  const issue = state.qualityIssues.find(item => item.issue_id === issueId);
  if (!issue) return;
  closeQualityDrawer();
  if (issue.domain_id !== state.domainMeta.id) await loadDomain(issue.domain_id, issue.topic_id);
  else await navigateToNode(issue.topic_id, true, true);
  renderBrowser();
  if (issue.target_type === "statement") {
    setTimeout(() => document.getElementById(`stmt-${issue.target_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  }
}

function exportQualityIssues() {
  const issues = state.qualityIssues;
  const packet = {
    schema_version: "optistacks-quality-review-packet-v1",
    exported_at: new Date().toISOString(),
    summary: {
      total: issues.length,
      open: issues.filter(issue => issue.status !== "resolved").length,
      resolved: issues.filter(issue => issue.status === "resolved").length,
      history_events: state.submissionHistory.length,
    },
    site_build: state.manifest?.built_at,
    issues,
    history: state.submissionHistory,
  };
  const blob = new Blob([JSON.stringify(packet, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `reasatlas-quality-review-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
  toast("Quality review JSON exported");
}

bootstrap();
