const state = {
  data: null,
  nodes: new Map(),
  parents: new Map(),
  paths: new Map(),
  statements: new Map(),
  statementNodes: new Map(),
  deferred: new Map(),
  expanded: new Set(),
  selectedNode: null,
  selectedDeferred: null,
  mode: "atlas",
  query: "",
  deferredPage: 1,
};

const PAGE_SIZE = 40;
const $ = selector => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>'"]/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[character]));
const formatNumber = value => new Intl.NumberFormat("en-US").format(Number(value) || 0);
const percent = value => Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : "—";
const titleCase = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());

function math(value, display = false) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/\\\(|\\\[|\$\$|\\begin\s*\{/.test(raw)) return esc(raw);
  return esc(display ? `\\[${raw}\\]` : `\\(${raw}\\)`);
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 1800);
}

async function bootstrap() {
  try {
    const response = await fetch("data/atlas.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Atlas data: HTTP ${response.status}`);
    state.data = await response.json();
    indexData();
    renderReleaseSummary();
    bindGlobalEvents();
    const route = parseRoute();
    if (route.mode === "deferred" && state.deferred.has(route.id)) {
      setMode("deferred", false);
      selectDeferred(route.id, false);
    } else {
      setMode("atlas", false);
      const rootId = state.data.roots[0].id;
      state.expanded.add(rootId);
      selectNode(state.nodes.has(route.id) ? route.id : rootId, false);
    }
  } catch (error) {
    $("#outline-view").innerHTML = `<div class="empty-state"><b>Atlas could not be loaded</b><span>${esc(error.message)}</span></div>`;
  }
}

function indexData() {
  const walk = (node, parent = null, path = []) => {
    const currentPath = [...path, node];
    state.nodes.set(node.id, node);
    state.paths.set(node.id, currentPath);
    if (parent) state.parents.set(node.id, parent.id);
    (node.statements || []).forEach(statement => {
      state.statements.set(statement.id, statement);
      state.statementNodes.set(statement.id, node.id);
    });
    (node.children || []).forEach(child => walk(child, node, currentPath));
  };
  state.data.roots.forEach(root => walk(root));
  state.data.deferred.forEach(item => state.deferred.set(item.id, item));
}

function renderReleaseSummary() {
  const summary = state.data.summary;
  $("#build-date").textContent = new Date(state.data.built_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  $("#node-count").textContent = formatNumber(summary.canonical_nodes + summary.proposed_topics_grouped);
  $("#deferred-count").textContent = formatNumber(summary.deferred_items);
  $("#source-total").textContent = `${formatNumber(summary.source_items)} items`;
  $("#release-id").textContent = state.data.source_run.run_id;
  const maximum = Math.max(...state.data.source_collections.map(source => source.items), 1);
  $("#source-list").innerHTML = state.data.source_collections.map(source => `
    <div class="source-row">
      <b title="${esc(source.name)}">${esc(source.name)}</b><span>${formatNumber(source.items)}</span>
      <div class="source-bar"><i style="width:${Math.max(4, source.items / maximum * 100)}%"></i></div>
    </div>`).join("");
}

function bindGlobalEvents() {
  $("#search-form").addEventListener("submit", event => event.preventDefault());
  $("#search-input").addEventListener("input", event => {
    state.query = event.target.value.trim();
    renderOutline();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && document.activeElement !== $("#search-input")) {
      event.preventDefault();
      $("#search-input").focus();
    }
    if (event.key === "Escape" && document.activeElement === $("#search-input")) {
      $("#search-input").value = "";
      state.query = "";
      $("#search-input").blur();
      renderOutline();
    }
  });
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
  $("#collapse-button").addEventListener("click", () => {
    state.expanded.clear();
    if (state.mode === "atlas") state.expanded.add(state.data.roots[0].id);
    renderOutline();
    toast("Outline collapsed");
  });
  window.addEventListener("hashchange", () => {
    const route = parseRoute();
    if (route.mode === "deferred" && state.deferred.has(route.id)) {
      setMode("deferred", false);
      selectDeferred(route.id, false);
    } else if (state.nodes.has(route.id)) {
      setMode("atlas", false);
      selectNode(route.id, false);
    }
  });
}

function parseRoute() {
  const raw = decodeURIComponent(location.hash.slice(1));
  const [mode, ...rest] = raw.split("/");
  if (mode === "deferred") return { mode, id: rest.join("/") };
  if (mode === "node") return { mode: "atlas", id: rest.join("/") };
  return { mode: "atlas", id: "" };
}

function setMode(mode, shouldUpdateRoute = true) {
  state.mode = mode === "deferred" ? "deferred" : "atlas";
  state.query = "";
  $("#search-input").value = "";
  document.querySelectorAll("[data-mode]").forEach(button => button.classList.toggle("active", button.dataset.mode === state.mode));
  $("#collapse-button").hidden = state.mode === "deferred";
  if (state.mode === "deferred") {
    $("#outline-eyebrow").textContent = "EVIDENCE REVIEW";
    $("#outline-title").textContent = "Deferred items";
    if (!state.selectedDeferred && state.data.deferred.length) state.selectedDeferred = state.data.deferred[0].id;
    renderDeferredDetail(state.deferred.get(state.selectedDeferred));
    if (shouldUpdateRoute && state.selectedDeferred) updateRouteForMode("deferred", state.selectedDeferred);
  } else {
    $("#outline-eyebrow").textContent = "ATLAS OUTLINE";
    $("#outline-title").textContent = "Knowledge tree";
    if (!state.selectedNode) state.selectedNode = state.data.roots[0].id;
    renderNodeDetail(state.nodes.get(state.selectedNode));
    if (shouldUpdateRoute) updateRouteForMode("atlas", state.selectedNode);
  }
  renderOutline();
}

function updateRouteForMode(mode, id) {
  const route = mode === "deferred" ? `#deferred/${encodeURIComponent(id)}` : `#node/${encodeURIComponent(id)}`;
  if (location.hash !== route) history.pushState(null, "", route);
}

function renderOutline() {
  const summary = $("#search-summary");
  if (state.query) {
    renderSearchResults();
    return;
  }
  summary.hidden = true;
  if (state.mode === "deferred") renderDeferredOutline();
  else renderTree();
}

function searchRows() {
  const terms = state.query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = text => {
    const haystack = String(text || "").toLocaleLowerCase();
    return terms.every(term => haystack.includes(term));
  };
  const rows = [];
  state.nodes.forEach(node => {
    if (matches([node.id, node.title, node.title_zh, node.role, node.scope_note].join(" "))) {
      rows.push({ type: "topic", id: node.id, title: node.title, meta: (state.paths.get(node.id) || []).map(item => item.title).join(" / ") });
    }
  });
  state.statements.forEach(statement => {
    if (matches([statement.id, statement.title, statement.content_kind, statement.statement_plain, statement.statement_latex, statement.source?.locator].join(" "))) {
      rows.push({ type: "statement", id: statement.id, title: statement.title, meta: statement.source?.locator || state.statementNodes.get(statement.id) });
    }
  });
  state.deferred.forEach(item => {
    if (matches([item.id, item.title, item.rationale, item.review_flags?.join(" "), item.source?.locator].join(" "))) {
      rows.push({ type: "deferred", id: item.id, title: item.title, meta: item.source?.locator || item.rationale });
    }
  });
  return rows;
}

function renderSearchResults() {
  const rows = searchRows();
  const shown = rows.slice(0, 150);
  const summary = $("#search-summary");
  summary.hidden = false;
  summary.textContent = `${formatNumber(rows.length)} results for “${state.query}”${rows.length > shown.length ? ` · showing first ${shown.length}` : ""}`;
  $("#outline-view").innerHTML = shown.length ? `<div class="result-list">${shown.map(row => `
    <button class="result-row" type="button" data-result-type="${row.type}" data-result-id="${esc(row.id)}">
      <small>${esc(row.type)}</small><b>${esc(row.title)}</b><span>${esc(row.meta)}</span>
    </button>`).join("")}</div>` : `<div class="empty-state"><b>No matches</b><span>Try a theorem name, notation, stable ID, or source locator.</span></div>`;
  document.querySelectorAll("[data-result-id]").forEach(button => button.addEventListener("click", () => openSearchResult(button.dataset.resultType, button.dataset.resultId)));
}

function openSearchResult(type, id) {
  state.query = "";
  $("#search-input").value = "";
  if (type === "deferred") {
    setMode("deferred", false);
    selectDeferred(id);
    return;
  }
  setMode("atlas", false);
  const nodeId = type === "statement" ? state.statementNodes.get(id) : id;
  selectNode(nodeId);
  if (type === "statement") {
    requestAnimationFrame(() => {
      const target = document.getElementById(`statement-${id}`);
      if (target) { target.open = true; target.scrollIntoView({ behavior: "smooth", block: "center" }); }
    });
  }
}

function revealNode(nodeId) {
  let current = nodeId;
  while (current) {
    state.expanded.add(current);
    current = state.parents.get(current);
  }
}

function renderTree() {
  $("#outline-view").innerHTML = `<ul class="tree-root">${state.data.roots.map(renderTreeNode).join("")}</ul>`;
  document.querySelectorAll("[data-toggle-node]").forEach(button => button.addEventListener("click", event => {
    event.stopPropagation();
    const id = button.dataset.toggleNode;
    state.expanded.has(id) ? state.expanded.delete(id) : state.expanded.add(id);
    renderTree();
  }));
  document.querySelectorAll("[data-select-node]").forEach(row => row.addEventListener("click", event => {
    if (!event.target.closest("[data-toggle-node]")) selectNode(row.dataset.selectNode);
  }));
}

function renderTreeNode(node) {
  const children = node.children || [];
  const open = state.expanded.has(node.id);
  return `<li class="tree-node">
    <div class="tree-row ${node.status === "proposed" ? "proposed" : ""} ${state.selectedNode === node.id ? "selected" : ""}" data-select-node="${esc(node.id)}">
      <button class="tree-toggle ${children.length ? (open ? "open" : "") : "leaf"}" type="button" data-toggle-node="${esc(node.id)}" aria-label="${open ? "Collapse" : "Expand"}"></button>
      <span class="tree-label"><small>${esc(node.display_number)} · ${esc(node.node_type)}</small><b title="${esc(node.title)}">${node.status === "proposed" ? "◇ " : ""}${esc(node.title)}</b></span>
      <span class="tree-count">${node.descendant_statement_count ? `<em>${formatNumber(node.descendant_statement_count)}</em>` : ""}${node.descendant_proposed_topic_count ? `<em class="proposal">+${formatNumber(node.descendant_proposed_topic_count)}</em>` : ""}</span>
    </div>
    ${children.length && open ? `<ul class="tree-children">${children.map(renderTreeNode).join("")}</ul>` : ""}
  </li>`;
}

function selectNode(nodeId, updateRoute = true) {
  if (!state.nodes.has(nodeId)) return;
  state.mode = "atlas";
  state.selectedNode = nodeId;
  revealNode(nodeId);
  renderTree();
  renderNodeDetail(state.nodes.get(nodeId));
  if (updateRoute) updateRouteForMode("atlas", nodeId);
}

function renderNodeDetail(node) {
  if (!node) return;
  const path = state.paths.get(node.id) || [node];
  const proposed = node.status === "proposed";
  const isRoot = node.id === state.data.roots[0].id;
  $("#detail-pane").innerHTML = `
    <header class="topic-hero">
      <div class="breadcrumbs">${path.map((item, index) => `${index ? "<i>/</i>" : ""}<span>${esc(item.title)}</span>`).join("")}</div>
      <div class="node-badges"><span class="badge ${proposed ? "proposed" : "accepted"}">${proposed ? "Proposed topic" : "Canonical tree"}</span><span class="badge">${esc(node.node_type)}</span><span class="badge">${esc(node.id)}</span></div>
      <h1>${esc(node.title)}</h1>
      ${node.title_zh ? `<p class="title-zh">${esc(node.title_zh)}</p>` : ""}
      <p class="topic-role">${esc(node.role || "This node organizes the source-aligned mathematical knowledge below it.")}</p>
      <div class="hero-metrics"><span><b>${formatNumber(node.direct_statement_count)}</b>direct items</span><span><b>${formatNumber(node.descendant_statement_count)}</b>subtree items</span><span><b>${formatNumber(node.descendant_proposed_topic_count)}</b>proposed topics</span><span><b>${formatNumber(node.descendant_relation_count)}</b>relations</span></div>
    </header>
    <div class="detail-body">
      ${isRoot ? renderOverview() : ""}
      ${proposed ? renderCandidateNote(node) : ""}
      ${renderChildren(node)}
      ${renderRelations(node)}
      ${renderStatements(node.statements || [])}
    </div>`;
  bindDetailLinks();
  typesetMath();
  $("#detail-pane").scrollTop = 0;
}

function renderOverview() {
  const summary = state.data.summary;
  return `
    <p class="overview-intro">This release keeps the 148-node mathematical backbone immutable and layers independently reviewed textbook evidence over it. Existing placements, proposed topic containers, cross-topic relations, and unresolved OCR evidence remain visibly distinct.</p>
    <div class="metrics-grid">
      ${metric(summary.source_items, "Source items")}
      ${metric(summary.placed_existing, "Existing placements")}
      ${metric(summary.proposed_topic_statements, "Proposed-topic items")}
      ${metric(summary.relation_candidates, "Relations")}
      ${metric(summary.deferred_items, "Deferred")}
    </div>
    <section class="section">
      <div class="section-heading"><h2>Ten-part reading path</h2><span>${formatNumber(summary.canonical_nodes)} canonical nodes</span></div>
      <div class="chapter-grid">${state.data.chapters.map(chapter => `
        <button class="chapter-card" type="button" data-node-link="${esc(chapter.id)}">
          <small>${esc(chapter.number)}</small><b>${esc(chapter.title)}</b><span>${formatNumber(chapter.statements)} items · ${formatNumber(chapter.proposed_topics)} proposals</span>
        </button>`).join("")}</div>
    </section>
    <section class="section">
      <div class="section-heading"><h2>Evidence integrity</h2><span>publication validation PASS</span></div>
      <div class="candidate-note"><b>All ${formatNumber(summary.accounted_source_items)} items are accounted for exactly once.</b>${formatNumber(summary.items_with_markdown_evidence)} items have Markdown evidence; ${formatNumber(summary.items_with_all_markdown_files)} have both requested witnesses. ${formatNumber(summary.missing_markdown_markers)} unmatched markers remain visible through the deferred and review metadata.</div>
    </section>`;
}

function metric(value, label) {
  return `<div class="metric-card"><strong>${formatNumber(value)}</strong><span>${esc(label)}</span></div>`;
}

function renderCandidateNote(node) {
  const reasons = node.candidate_reasons || [];
  return `<div class="candidate-note"><b>Candidate container · ${formatNumber(node.candidate_source_count)} supporting source item${node.candidate_source_count === 1 ? "" : "s"}</b>${esc(node.scope_note || reasons[0] || "This topic was proposed during the reviewed directory assessment.")}${reasons.length > 1 ? `<br><small>${formatNumber(reasons.length)} distinct placement rationales retained.</small>` : ""}</div>`;
}

function renderChildren(node) {
  const children = node.children || [];
  if (!children.length) return "";
  return `<section class="section"><div class="section-heading"><h2>Child topics</h2><span>${formatNumber(children.length)}</span></div><div class="child-grid">${children.map(child => `
    <button class="child-card" type="button" data-node-link="${esc(child.id)}"><b>${child.status === "proposed" ? "◇ " : ""}${esc(child.title)}</b><span>→</span></button>`).join("")}</div></section>`;
}

function renderRelations(node) {
  const relations = node.relations || [];
  if (!relations.length) return "";
  return `<section class="section"><div class="section-heading"><h2>Reviewed relation candidates</h2><span>${formatNumber(relations.length)}</span></div><div class="relation-grid">${relations.map(relation => {
    const target = state.nodes.get(relation.target_node_id);
    return `<button class="relation-card" type="button" ${target ? `data-node-link="${esc(target.id)}"` : "disabled"}><small>${esc(titleCase(relation.relation_type))} · ${percent(relation.review_confidence)}</small><b>${esc(target?.title || relation.target_node_id)}</b><p>${esc(relation.rationale)}</p></button>`;
  }).join("")}</div></section>`;
}

const GROUPS = [
  ["Definitions", new Set(["definition", "representation", "notation"])],
  ["Conditions", new Set(["condition", "assumption"])],
  ["Algorithms", new Set(["algorithm"])],
  ["Theorems & properties", new Set(["theorem", "property", "proposition", "lemma", "corollary", "certificate", "principle", "duality"])],
  ["Counterexamples & boundaries", new Set(["counterexample", "failure_boundary"])],
  ["Other knowledge", null],
];

function groupedStatements(statements) {
  const remaining = new Set(statements);
  return GROUPS.map(([title, kinds]) => {
    const rows = statements.filter(statement => remaining.has(statement) && (!kinds || kinds.has(statement.content_kind)));
    rows.forEach(row => remaining.delete(row));
    return [title, rows];
  }).filter(([, rows]) => rows.length);
}

function renderStatements(statements) {
  if (!statements.length) return "";
  let offset = 0;
  return `<section class="section"><div class="section-heading"><h2>Knowledge statements</h2><span>${formatNumber(statements.length)} reviewed placements</span></div><div class="statement-list">${groupedStatements(statements).map(([group, rows]) => `
    <div class="statement-group"><div class="section-heading"><h2>${esc(group)}</h2><span>${formatNumber(rows.length)}</span></div>${rows.map(statement => renderStatement(statement, offset++)).join("")}</div>`).join("")}</div></section>`;
}

function renderStatement(statement, index) {
  const source = statement.source || {};
  const qualityClass = source.quality_status === "degraded" ? "quality-degraded" : "accepted";
  return `<details class="statement-card" id="statement-${esc(statement.id)}" ${index === 0 ? "open" : ""}>
    <summary><b>${esc(statement.title)}</b><span class="statement-badges"><span class="badge">${esc(statement.content_kind)}</span><span class="badge ${statement.placement === "proposed_node" ? "proposed" : "accepted"}">${statement.placement === "proposed_node" ? "new topic" : "placed"}</span><span class="badge">${percent(statement.review_confidence)}</span></span></summary>
    <div class="statement-content">
      ${statement.statement_plain ? `<p class="plain-statement">${esc(statement.statement_plain)}</p>` : ""}
      ${statement.statement_latex ? `<pre class="formal-source">${esc(statement.statement_latex)}</pre>` : ""}
      <div class="meta-grid">
        ${statement.assumptions_latex?.length ? `<div class="meta-block full"><label>Assumptions</label><ul class="math-list">${statement.assumptions_latex.map(value => `<li>${math(value)}</li>`).join("")}</ul></div>` : ""}
        ${statement.conclusion_latex ? `<div class="meta-block full"><label>Conclusion</label><div>${math(statement.conclusion_latex, true)}</div></div>` : ""}
        ${statement.scope_note ? `<div class="meta-block full"><label>Scope</label><p>${esc(statement.scope_note)}</p></div>` : ""}
        ${statement.review_flags?.length ? `<div class="meta-block full"><label>Independent review flags</label><ul class="flag-list">${statement.review_flags.map(flag => `<li>${esc(flag)}</li>`).join("")}</ul></div>` : ""}
      </div>
      ${renderAssessment(statement.directory_assessment)}
      ${renderSource(source, statement.id, qualityClass)}
    </div>
  </details>`;
}

function renderAssessment(assessment) {
  if (!assessment) return "";
  return `<div class="assessment"><b>Directory assessment · ${esc(titleCase(assessment.status))} / ${esc(titleCase(assessment.recommendation))}</b>${esc(assessment.rationale)}${assessment.preferred_home_node_id ? `<br>Preferred home: <code>${esc(assessment.preferred_home_node_id)}</code>` : ""}</div>`;
}

function renderSource(source, id, qualityClass = "accepted") {
  const markdown = source.markdown || [];
  const degraded = source.quality_status === "degraded";
  return `<div class="source-meta"><div><span class="badge">${esc(source.collection || "Source")}</span><span class="badge">${esc(source.environment || "item")}</span><span class="badge ${qualityClass}"${degraded ? ' title="OCR or source-document quality warning; not a Codex runtime status"' : ""}>${esc(source.quality_status || "unknown")} source</span>${markdown.map(item => `<span class="badge">${esc(item.role || item.name)}</span>`).join("")}</div><p>${source.chapter ? `${esc(source.chapter)}<br>` : ""}${esc(source.locator || "No source locator supplied")}</p>${degraded ? '<p class="quality-explanation">“Degraded” marks an OCR/source-document quality warning; it does not mean Codex or <code>codex_home</code> failed.</p>' : ""}<p><code>${esc(id)}</code></p></div>`;
}

function bindDetailLinks() {
  document.querySelectorAll("[data-node-link]").forEach(button => button.addEventListener("click", () => selectNode(button.dataset.nodeLink)));
}

function renderDeferredOutline() {
  const rows = state.data.deferred;
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  state.deferredPage = Math.min(Math.max(1, state.deferredPage), pages);
  const start = (state.deferredPage - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);
  $("#outline-view").innerHTML = `<div class="deferred-list">${pageRows.map(item => `
    <button class="deferred-card ${state.selectedDeferred === item.id ? "selected" : ""}" type="button" data-deferred-id="${esc(item.id)}"><b>${esc(item.title)}</b><small>${percent(item.review_confidence)}</small><span>${esc(item.source.locator || item.rationale)}</span></button>`).join("")}</div>
    <div class="pagination"><button id="previous-page" type="button" ${state.deferredPage === 1 ? "disabled" : ""}>← Previous</button><span>${state.deferredPage} / ${pages}</span><button id="next-page" type="button" ${state.deferredPage === pages ? "disabled" : ""}>Next →</button></div>`;
  document.querySelectorAll("[data-deferred-id]").forEach(button => button.addEventListener("click", () => selectDeferred(button.dataset.deferredId)));
  $("#previous-page").addEventListener("click", () => { state.deferredPage -= 1; renderDeferredOutline(); });
  $("#next-page").addEventListener("click", () => { state.deferredPage += 1; renderDeferredOutline(); });
}

function selectDeferred(id, updateRoute = true) {
  if (!state.deferred.has(id)) return;
  state.mode = "deferred";
  state.selectedDeferred = id;
  const index = state.data.deferred.findIndex(item => item.id === id);
  if (index >= 0) state.deferredPage = Math.floor(index / PAGE_SIZE) + 1;
  renderDeferredOutline();
  renderDeferredDetail(state.deferred.get(id));
  if (updateRoute) updateRouteForMode("deferred", id);
}

function renderDeferredDetail(item) {
  if (!item) return;
  const source = item.source || {};
  $("#detail-pane").innerHTML = `
    <header class="topic-hero deferred-hero">
      <div class="breadcrumbs"><span>Bruhat–Tits Theory</span><i>/</i><span>Evidence review</span><i>/</i><span>${esc(item.id)}</span></div>
      <div class="node-badges"><span class="badge deferred">Deferred</span><span class="badge">${esc(item.content_kind)}</span><span class="badge">${percent(item.review_confidence)} review confidence</span></div>
      <h1>${esc(item.title)}</h1>
      <p class="topic-role">${esc(item.rationale || "This source item requires additional evidence or directory adjudication before publication.")}</p>
    </header>
    <div class="detail-body">
      <div class="candidate-note"><b>Why this item is not in the published tree</b>Deferred evidence is preserved rather than silently discarded. Review flags and source quality below record the exact boundary.</div>
      ${item.statement_plain || item.statement_latex ? `<section class="section"><div class="section-heading"><h2>Candidate statement</h2><span>not published</span></div>${item.statement_plain ? `<p class="plain-statement">${esc(item.statement_plain)}</p>` : ""}${item.statement_latex ? `<pre class="formal-source">${esc(item.statement_latex)}</pre>` : ""}</section>` : ""}
      ${item.review_flags?.length ? `<section class="section"><div class="section-heading"><h2>Review flags</h2><span>${formatNumber(item.review_flags.length)}</span></div><div class="meta-block full"><ul class="flag-list">${item.review_flags.map(flag => `<li>${esc(flag)}</li>`).join("")}</ul></div></section>` : ""}
      ${renderAssessment(item.directory_assessment)}
      <section class="section"><div class="section-heading"><h2>Source evidence</h2><span>${esc(item.mapping_status || "unmapped")}</span></div>${renderSource(source, item.id, source.quality_status === "degraded" ? "quality-degraded" : "accepted")}</section>
    </div>`;
  typesetMath();
  $("#detail-pane").scrollTop = 0;
}

function typesetMath() {
  if (!window.MathJax?.typesetPromise) return;
  window.MathJax.typesetClear?.([$("#detail-pane")]);
  window.MathJax.typesetPromise([$("#detail-pane")]).catch(() => {});
}

bootstrap();
